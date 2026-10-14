"""SimulatedDevice through the real path: compile_sweep + Executor, against the model as oracle."""

import numpy as np
import pytest

from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.protocols import LevelSense, LevelSource, Sequencer
from qdt_lab.stream import assemble
from qdt_schemas.activity import SequencerParameter, SequencerProgram, SequencerResult
from qdt_sim import DeviceNoise, SimulatedDevice, WhiteNoise
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, stability

EMITTERS = {"simulated": SimulatedEmitter()}


def quiet() -> SimulatedDevice:
    return default_device(seed=0, noise=False, sample_charge=False)


def run(definition, device):
    plan = compile_sweep(definition, default_stand(), EMITTERS)
    return plan, assemble(plan.dataset, Executor(plan, {DEVICE_ID: device}).run().frames())


def test_device_satisfies_the_three_protocols():
    d = quiet()
    assert isinstance(d, LevelSource) and isinstance(d, LevelSense) and isinstance(d, Sequencer)


def test_levels_and_sense():
    d = quiet()
    d.set("P1", 0.05)
    assert d.get("P1") == 0.05
    assert d.sense("sensor") == pytest.approx(d.model.current(d.gate_vector()), rel=1e-12)
    with pytest.raises(ValueError, match="sense the sensor"):
        d.sense("P1")
    with pytest.raises(ValueError, match="unknown channel"):
        d.set("nope", 0.0)


def test_compile_rejects_other_backends():
    program = SequencerProgram(
        backend="qua",
        body="#",
        parameters=(SequencerParameter(name="n", unit=""),),
        results=(SequencerResult(name="d", dims=("n",), dtype="int64", unit=""),),
    )
    with pytest.raises(ValueError, match="backend 'simulated'"):
        quiet().compile(program)


def test_stability_sweep_equals_the_model_on_the_grid():
    """No noise, mean occupation: the executed sweep is the model evaluated at every (P1, P2 pulse)."""
    plan, out = run(stability(6, 9, p1=(-0.02, 0.04), p2=(-0.03, 0.05)), quiet())
    assert out["I_sensor"].shape == (6, 9)
    p1 = np.linspace(-0.02, 0.04, 6)
    p2 = np.linspace(-0.03, 0.05, 9)
    v = np.zeros((6, 9, 3))
    v[..., 0] = p1[:, None]
    v[..., 1] = p2[None, :]  # DC P2 is 0, the pulse adds on top
    expected = quiet().model.current(v)
    np.testing.assert_allclose(out["I_sensor"].values, expected, rtol=1e-12)
    np.testing.assert_allclose(out["P2"].values, p2)
    assert plan.dataset.data_vars[0].unit == "A"


def test_pulse_adds_to_dc_level():
    d = quiet()
    d.set("P2", 0.01)
    _, out = run(stability(2, 4, p1=(0.0, 0.0), p2=(0.0, 0.03)), d)
    v = np.zeros((4, 3))
    v[:, 1] = 0.01 + np.linspace(0.0, 0.03, 4)
    np.testing.assert_allclose(out["I_sensor"].values[0], d.model.current(v), rtol=1e-12)


def test_kept_shots_sample_the_charge_state_and_readout_noise():
    d = SimulatedDevice(noise=DeviceNoise(readout=WhiteNoise(2e-11, seed=1)), seed=3)
    _, out = run(stability(2, 3, shots=50), d)
    assert out["I_sensor"].shape == (2, 3, 50)
    assert out["I_sensor"].values.std(axis=-1).min() > 0, "shots differ"
    plan_m, out_m = run(stability(2, 3, shots=50, reduce="mean"), d)
    assert out_m["I_sensor"].shape == (2, 3)
    assert plan_m.dataset.attrs["I_sensor.reduced"] == "shot:mean"


def test_clock_advances_with_integration_and_pulses():
    d = quiet()
    t0 = d.clock_s
    run(stability(1, 2, p1=(0.0, 0.0), p2=(0.0, 0.01)), d)
    # per pixel: 500 ns step + 2000 ns measure + shot overhead
    assert d.clock_s - t0 == pytest.approx(2 * (2500e-9 + d.shot_overhead_s), rel=1e-9)


def test_noise_drifts_the_map_between_repeats():
    _, out = run(stability(4, 6, repeats=2), default_device(seed=1, noise=True))
    assert out["I_sensor"].shape == (2, 4, 6)
    a, b = out["I_sensor"].values
    assert not np.allclose(a, b, rtol=1e-3, atol=0)


def test_from_config_takes_the_sensor_aperture_from_the_channel_map():
    stand = default_stand()
    channels = tuple(
        c.model_copy(update={"integration_s": 5e-3}) if c.channel == "sensor" else c
        for c in stand.instrument_channels(DEVICE_ID)
    )
    d = SimulatedDevice.from_config(stand.instrument(DEVICE_ID), channels, noise=DeviceNoise())
    t0 = d.clock_s
    d.sense("sensor")
    assert d.clock_s - t0 == pytest.approx(5e-3 + d.shot_overhead_s, rel=1e-12)


def test_from_config_rejects_a_quantity_that_contradicts_the_role():
    stand = default_stand()
    channels = tuple(
        c.model_copy(update={"quantity": "voltage"}) if c.channel == "sensor" else c
        for c in stand.instrument_channels(DEVICE_ID)
    )
    with pytest.raises(ValueError, match="sensor"):
        SimulatedDevice.from_config(stand.instrument(DEVICE_ID), channels)


def chopped(shots: int = 1, reduce: str = "keep"):
    """Chopped readout: measure at the swept level, then at the swept level + one axis step, subtract."""
    from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition, SymbolBinding
    from qdt_schemas.pulse import Affine, Difference, Measure, PulseSequence, Step, Symbol

    v = Symbol(name="v_p2", unit="V")
    p2 = SweepAxis(name="P2", channel="P2_pulse", start=0.03, stop=0.17, num=15)  # step 0.01 V
    seq = PulseSequence(
        name="chopped",
        body=(
            Step(channel="P2_pulse", level=v, duration=500),
            Measure(channel="sensor", duration=2000, result="I_on"),
            Step(channel="P2_pulse", level=Affine(symbol=v, offset=p2.step), duration=500),
            Measure(channel="sensor", duration=2000, result="I_off"),
            Difference(result="dI", a="I_on", b="I_off"),
        ),
    )
    return SweepDefinition(
        name="chopped",
        axes=(SweepAxis(name="P1", channel="P1", start=0.03, stop=0.17, num=4), p2),
        stage=SequencerStage(
            instrument=DEVICE_ID,
            axes=("P2",),
            sequence=seq,
            bindings=(SymbolBinding(symbol="v_p2", axis="P2"),),
            shots=shots,
            reduce={r: reduce for r in ("I_on", "I_off", "dI")} if reduce != "keep" else {},
        ),
    )


def test_affine_level_follows_the_swept_symbol():
    _, xds = run(chopped(), quiet())
    on, off = xds["I_on"].values, xds["I_off"].values
    # the chop point is one axis step up: I_off at index i is I_on at index i + 1
    np.testing.assert_allclose(off[:, :-1], on[:, 1:], rtol=1e-12)


def test_difference_is_per_shot_and_recorded_beside_the_measures():
    plan, xds = run(chopped(), quiet())
    assert {v.name for v in plan.dataset.data_vars} == {"I_on", "I_off", "dI"}
    assert next(v for v in plan.dataset.data_vars if v.name == "dI").unit == "A"
    np.testing.assert_allclose(
        xds["dI"].values, xds["I_on"].values - xds["I_off"].values, rtol=1e-12
    )
    # with charge sampling and readout noise, kept shots: the difference is taken shot by shot
    _, noisy = run(chopped(shots=3), default_device(seed=1))
    assert noisy["dI"].dims[-1] == "shot"
    np.testing.assert_allclose(noisy["dI"].values, noisy["I_on"].values - noisy["I_off"].values)
    # reduced on the sequencer: the mean of differences equals the difference of means
    _, mean = run(chopped(shots=3, reduce="mean"), default_device(seed=1))
    np.testing.assert_allclose(
        mean["dI"].values, mean["I_on"].values - mean["I_off"].values, rtol=1e-9, atol=1e-18
    )


def test_operating_point_level_is_what_pulses_add_to():
    """ADR 0038: P2 held at 50 mV by the operating point, its pulse swept 50 mV lower, is the same map
    as no DC and the pulse swept over the absolute range."""
    from qdt_schemas.activity import FixedLevel

    absolute = stability(6, 8, p1=(0.03, 0.17), p2=(0.03, 0.17))
    held = stability(6, 8, p1=(0.03, 0.17), p2=(-0.02, 0.12)).model_copy(
        update={"levels": (FixedLevel(channel="P2", value=0.05),)}
    )
    held = type(held).model_validate(held.model_dump())
    plan, a = run(absolute, quiet())
    plan_h, b = run(held, quiet())
    assert "P2" in {c.logical for c in plan_h.channels} and "P2" not in {c.logical for c in plan.channels}
    np.testing.assert_allclose(b["I_sensor"].values, a["I_sensor"].values, rtol=1e-12)


def test_operating_point_needs_a_level_source():
    from qdt_schemas.activity import FixedLevel

    d = stability(4, 4).model_copy(update={"levels": (FixedLevel(channel="sensor", value=0.0),)})
    d = type(d).model_validate(d.model_dump())
    with pytest.raises(ValueError, match="one terminal, one role|lacks capability"):
        run(d, quiet())
