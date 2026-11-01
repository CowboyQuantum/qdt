"""SimulatedDevice through the real path: compile_sweep + Executor, against Phantom's noise-free
`Device.at` as oracle (ADR 0088)."""

import numpy as np
import pytest

from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.protocols import LevelSense, LevelSource, Sequencer
from qdt_lab.stream import assemble
from qdt_schemas.activity import SequencerParameter, SequencerProgram, SequencerResult
from qdt_sim import SimulatedDevice
from qdt_sim.scenarios import (
    DEVICE_ID,
    DEVICES,
    LATTICE_SPAN_V,
    SENSOR_SET_V,
    default_device,
    default_stand,
    load_device,
    programmed,
    stability,
    start,
)

EMITTERS = {"simulated": SimulatedEmitter()}


def quiet() -> SimulatedDevice:
    return default_device(seed=0, noise=False, sample_charge=False)


def current(**levels) -> np.ndarray:
    """The default device's noise-free sensor current with the named gates at `levels` (arrays
    broadcast) and every other gate at its starting level (`start`, ADR 0090)."""
    device = load_device()
    shape = np.broadcast(*(np.asarray(x) for x in levels.values())).shape
    first = [start()[g] for g in device.gate_names]
    v = np.broadcast_to(np.array(first), (*shape, len(device.gate_names))).copy()
    for gate, x in levels.items():
        v[..., device.gate_names.index(gate)] = x
    return device.at(v).sensor_current_a


P2 = programmed()["P2"]


def run(definition, device):
    plan = compile_sweep(definition, default_stand(), EMITTERS)
    return plan, assemble(plan.dataset, Executor(plan, {DEVICE_ID: device}).run().frames())


def test_device_satisfies_the_three_protocols():
    d = quiet()
    assert isinstance(d, LevelSource) and isinstance(d, LevelSense) and isinstance(d, Sequencer)


def test_levels_and_sense():
    d = quiet()
    d.set("P1", 0.62)
    assert d.get("P1") == 0.62
    assert d.get("P2") == P2  # every gate starts at the programmed point but the sensor gate
    assert d.get("SG") == start()["SG"] != programmed()["SG"]
    assert d.sense("sensor") == pytest.approx(float(current(P1=0.62)), rel=1e-12)
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
    """No noise, mean occupation: the executed sweep is the device evaluated at every (P1, P2 pulse)."""
    plan, out = run(stability(6, 9, p1=(0.58, 0.64), p2=(-0.03, 0.05)), quiet())
    assert out["I_sensor"].shape == (6, 9)
    p1 = np.linspace(0.58, 0.64, 6)
    p2 = np.linspace(-0.03, 0.05, 9)
    expected = current(P1=p1[:, None], P2=P2 + p2[None, :])  # the pulse adds to P2's programmed DC
    np.testing.assert_allclose(out["I_sensor"].values, expected, rtol=1e-12)
    np.testing.assert_allclose(out["P2"].values, p2)
    assert plan.dataset.data_vars[0].unit == "A"


def test_pulse_adds_to_dc_level():
    d = quiet()
    d.set("P2", 0.61)
    _, out = run(stability(2, 4, p1=(0.6, 0.6), p2=(0.0, 0.03)), d)
    expected = current(P1=0.6, P2=0.61 + np.linspace(0.0, 0.03, 4))
    np.testing.assert_allclose(out["I_sensor"].values[0], expected, rtol=1e-12)


def test_kept_shots_sample_the_charge_state_and_readout_noise():
    d = SimulatedDevice(load_device(), seed=3)
    _, out = run(stability(2, 3, shots=50), d)
    assert out["I_sensor"].shape == (2, 3, 50)
    assert out["I_sensor"].values.std(axis=-1).min() > 0, "shots differ"
    plan_m, out_m = run(stability(2, 3, shots=50, reduce="mean"), d)
    assert out_m["I_sensor"].shape == (2, 3)
    assert plan_m.dataset.attrs["I_sensor.reduced"] == "shot:mean"


def test_clock_advances_with_integration_and_pulses():
    d = quiet()
    t0 = d.clock_s
    run(stability(1, 2, p1=(0.6, 0.6), p2=(0.0, 0.01), measure_ns=2000), d)
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
    d = SimulatedDevice.from_config(
        stand.instrument(DEVICE_ID), channels, load_device(), noise=False
    )
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
        SimulatedDevice.from_config(stand.instrument(DEVICE_ID), channels, load_device())


def chopped(shots: int = 1, reduce: str = "keep"):
    """Chopped readout: measure at the swept level, then at the swept level + one axis step, subtract."""
    from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition, SymbolBinding
    from qdt_schemas.pulse import Affine, Difference, Measure, PulseSequence, Step, Symbol

    v = Symbol(name="v_p2", unit="V")
    p2 = SweepAxis(name="P2", channel="P2_pulse", start=-0.07, stop=0.07, num=15)  # step 0.01 V
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
        axes=(SweepAxis(name="P1", channel="P1", start=0.53, stop=0.67, num=4), p2),
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
    """ADR 0038: P2 held 50 mV above its programmed level by the operating point, its pulse swept 50 mV
    lower, is the same map as the programmed DC and the pulse swept over the higher range."""
    from qdt_schemas.activity import FixedLevel

    absolute = stability(6, 8, p1=(0.53, 0.67), p2=(0.03, 0.17))
    held = stability(6, 8, p1=(0.53, 0.67), p2=(-0.02, 0.12)).model_copy(
        update={"levels": (FixedLevel(channel="P2", value=P2 + 0.05),)}
    )
    held = type(held).model_validate(held.model_dump())
    plan, a = run(absolute, quiet())
    plan_h, b = run(held, quiet())
    assert "P2" in {c.logical for c in plan_h.channels} and "P2" not in {
        c.logical for c in plan.channels
    }
    np.testing.assert_allclose(b["I_sensor"].values, a["I_sensor"].values, rtol=1e-12)


def test_operating_point_needs_a_level_source():
    from qdt_schemas.activity import FixedLevel

    d = stability(4, 4).model_copy(update={"levels": (FixedLevel(channel="sensor", value=0.0),)})
    d = type(d).model_validate(d.model_dump())
    with pytest.raises(ValueError, match="one terminal, one role|lacks capability"):
        run(d, quiet())


def test_a_triggered_axis_on_the_device_gives_the_same_map_as_software_stepping():
    """ADR 0064, 0066: the device is its own sequencer, so on the simulated stand 'auto' triggers the
    DC axis with no marker line; every loaded list sits on the point the program is at. The map is
    the one the executor gets by setting each point itself."""
    from qdt_lab.protocols import TriggeredLevelSource

    assert isinstance(quiet(), TriggeredLevelSource)
    auto = stability(6, 9, p1=(0.58, 0.64), p2=(-0.03, 0.05))
    software = auto.model_copy(
        update={"axes": (auto.axes[0].model_copy(update={"stepping": "software"}), auto.axes[1])}
    )
    plan, out = run(auto, quiet())
    assert [(p.axis, p.pacing, p.lines) for p in plan.pacing] == [
        ("P1", "triggered", ()),
        ("P2", "sequencer", ()),
    ]
    assert [p.name for p in plan.stage_program.parameters][:1] == ["n_P1"]
    assert plan.stage_program.results[0].dims == ("n_P1", "n_P2")
    software_plan, expected = run(software, quiet())
    assert software_plan.pacing_of("P1").pacing == "software"
    np.testing.assert_allclose(out["I_sensor"].values, expected["I_sensor"].values, rtol=1e-12)
    d = quiet()
    d.load("P1", (0.1, 0.2))
    d.advance("P1")
    assert d.get("P1") == 0.1
    d.release("P1")
    assert d.get("P1") == 0.1
    with pytest.raises(ValueError, match="no list loaded"):
        d.advance("P1")


def test_a_host_stepped_axis_read_in_a_one_measure_shot_is_the_model_at_each_point():
    """ADR 0068: no stage axis, one shot, the DC axis stepped from the host: one measure per point, the
    value the device gives there (what a DC sweep read in the shot records on an unwired stand)."""
    from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition
    from qdt_schemas.pulse import Measure, PulseSequence

    definition = SweepDefinition(
        name="read in the shot, host-stepped",
        axes=(
            SweepAxis(name="P1", channel="P1", start=0.58, stop=0.64, num=7, stepping="software"),
        ),
        stage=SequencerStage(
            instrument=DEVICE_ID,
            sequence=PulseSequence(
                name="read", body=(Measure(channel="sensor", duration=1000, result="I"),)
            ),
        ),
    )
    plan, out = run(definition, quiet())
    assert plan.pacing_of("P1").pacing == "software"
    expected = current(P1=np.linspace(0.58, 0.64, 7))
    np.testing.assert_allclose(out["I"].values, expected, rtol=1e-12)


def test_a_capture_on_the_devices_own_sensor_records_the_device_over_the_window():
    """ADR 0069: the device is its own scope. A capture on the sensor channel inside the shot is the
    sensor current at the shot's levels, `num` samples over the window, one record per shot; over a
    triggered DC axis the records lie at the stepped points, and the plan needs no scope at all."""
    from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition
    from qdt_schemas.pulse import Capture, PulseSequence, Step

    definition = SweepDefinition(
        name="record the sensor",
        axes=(SweepAxis(name="P1", channel="P1", start=0.58, stop=0.64, num=4),),
        stage=SequencerStage(
            instrument=DEVICE_ID,
            sequence=PulseSequence(
                name="step and record",
                body=(
                    Step(channel="P2_pulse", level=0.01, duration=200),
                    Capture(channel="sensor", duration=2000, num=8, result="trace"),
                ),
            ),
            shots=2,
        ),
    )
    plan, out = run(definition, quiet())
    assert plan.pacing_of("P1").pacing == "triggered"  # the device triggers itself (ADR 0066)
    assert [r.dims for r in plan.stage_program.results] == [("n_P1", "shots", "n_trace")]
    assert {(c.logical, c.role) for c in plan.channels} == {
        ("P1", "triggered_level_source"),
        ("P2_pulse", "sequencer"),
        ("sensor", "sequencer"),
    }
    assert out["trace"].dims == ("P1", "shot", "time") and out["trace"].shape == (4, 2, 8)
    expected = current(P1=np.linspace(0.58, 0.64, 4), P2=P2 + 0.01)  # the pulse adds to P2's DC
    np.testing.assert_allclose(
        out["trace"].values, np.broadcast_to(expected[:, None, None], (4, 2, 8)), rtol=1e-12
    )
    with pytest.raises(ValueError, match="capture on 'P1', which is not the sensor"):
        quiet().compile(
            compile_sweep(
                definition.model_copy(
                    update={
                        "stage": definition.stage.model_copy(
                            update={
                                "sequence": PulseSequence(
                                    name="wrong",
                                    body=(
                                        Capture(channel="P1", duration=2000, num=8, result="trace"),
                                    ),
                                )
                            }
                        ),
                        "axes": (SweepAxis(name="P2", channel="P2", start=0.0, stop=0.1, num=2),),
                    }
                ),
                default_stand(),
                EMITTERS,
            ).stage_program
        )


def test_consecutive_scope_captures_advance_the_clock_once_by_the_longest_window():
    """ADR 0070: two scope channels captured back to back in the shot open together: the device's
    clock advances by the longest window once per shot, not by the windows in turn."""
    from qdt_lab.simulated import SimulatedWaveformSense
    from qdt_schemas.activity import SequencerStage, SweepDefinition
    from qdt_schemas.pulse import Capture, PulseSequence, Step
    from qdt_schemas.stand import ChannelMap, InstrumentConfig

    base = default_stand()
    stand = base.model_copy(
        update={
            "instruments": (
                *base.instruments,
                InstrumentConfig(id="scope", backend="simulated", capabilities=("waveform_sense",)),
            ),
            "channels": (
                *base.channels,
                ChannelMap(logical="scope1", instrument="scope", channel="1", quantity="voltage"),
                ChannelMap(logical="scope3", instrument="scope", channel="3", quantity="voltage"),
            ),
        }
    )
    definition = SweepDefinition(
        name="two windows",
        stage=SequencerStage(
            instrument=DEVICE_ID,
            sequence=PulseSequence(
                name="step and two windows",
                body=(
                    Step(channel="P2_pulse", level=0.01, duration=1000),
                    Capture(channel="scope1", duration=4000, num=40, result="a"),
                    Capture(channel="scope3", duration=2000, num=20, result="b"),
                ),
            ),
            shots=3,
        ),
    )
    device = quiet()
    t0 = device.clock_s
    plan = compile_sweep(definition, stand, EMITTERS)
    frames = list(
        Executor(
            plan,
            {DEVICE_ID: device, "scope": SimulatedWaveformSense(noise=0.0)},
            sleep=lambda s: None,
        )
        .run()
        .frames()
    )
    assert len(frames) == 6  # three records on each channel
    assert device.clock_s - t0 == pytest.approx(3 * (1000e-9 + 4000e-9), rel=1e-9)


def test_the_stand_wires_every_gate_and_a_gate_without_a_channel_holds_the_programmed_point():
    """Step 6d deliverable 6: a DC channel per gate, pulse lines on the plungers, the bias, the sensor."""
    device = load_device()
    logical = {c.logical for c in default_stand().channels}
    assert logical == {*device.gate_names, "P1_pulse", "P2_pulse", "bias", "bias_pulse", "sensor"}
    d = SimulatedDevice(device, {"P1": "P1", "sensor": "sensor"}, noise=False, sample_charge=False)
    assert d.levels()["B_M"] == programmed()["B_M"] and d.levels()["bias"] == 50e-6
    assert d.levels()["SG"] == programmed()["SG"]  # built without `levels`: the programmed point
    assert d.sense("sensor") == pytest.approx(float(current(SG=programmed()["SG"])), rel=1e-12)


def test_a_fresh_stand_starts_at_the_programmed_point_with_the_sensor_gate_where_it_reads():
    """ADR 0090: `start` moves only the sensor gate, to the committed level, on a committed device;
    a device that is not committed starts at its programmed point; `levels` overrides it."""
    device = load_device()
    first = start(device)
    assert {g for g in first if first[g] != programmed()[g]} == {"SG"}
    assert first["SG"] == SENSOR_SET_V["two-dot-sige-a"]
    assert default_device(noise=False).levels()["SG"] == first["SG"]
    assert default_device(noise=False, levels={"SG": 0.5}).levels()["SG"] == 0.5
    moved = type(device).loads(device.dumps().replace('"seed": 2', '"seed": 99', 1))
    assert start(moved) == programmed(moved)
    # there the sensor reads: a nanoamp-scale current, not the near-zero one between peaks
    assert abs(float(current())) > 1e3 * abs(float(current(SG=programmed()["SG"])))


def test_the_stand_starts_where_the_middle_barrier_sets_the_honeycomb():
    """ADR 0091: on Phantom 0.4.0 the plungers move the interdot coupling as much as B_M does, so part
    of a stability window about the start is one merged dot (Phantom's triple-point splitting near 1).
    The stand keeps the programmed plungers, where B_M moves that part: closing it shrinks, opening it
    grows. Below the compiled plungers B_M barely acts, which is why the start is not moved there."""

    def merged(device, **moved):
        x, at = np.linspace(-LATTICE_SPAN_V, LATTICE_SPAN_V, 41), start(device) | moved
        v = np.tile([at[g] for g in device.gate_names], (x.size, x.size, 1))
        v[..., device.gate_names.index("P1")] += x[:, None]
        v[..., device.gate_names.index("P2")] += x[None, :]
        return float((np.asarray(device.at(v).interdot_splitting) > 0.5).mean())

    for name in DEVICES:
        device = load_device(name)
        b_m = programmed(device)["B_M"]
        assert 0.3 < merged(device) < 0.5, name
        assert merged(device, B_M=b_m - 0.06) < merged(device) - 0.15 < merged(device, B_M=b_m + 0.04)


def test_the_noise_seed_replays_a_realisation_and_another_seed_draws_a_new_one():
    def read(seed):
        _, out = run(stability(3, 4, measure_ns=2000), default_device(seed=seed))
        return out["I_sensor"].values

    np.testing.assert_array_equal(read(4), read(4))
    assert not np.allclose(read(4), read(5), rtol=1e-3, atol=0)


def test_a_device_file_that_hashes_otherwise_or_is_not_committed_is_refused():
    with pytest.raises(ValueError, match="hashes to"):
        load_device("two-dot-sige-a", "0" * 64)
    with pytest.raises(ValueError, match="no committed device"):
        load_device("../../etc/passwd")


def test_qdt_sim_holds_no_physics_and_stays_under_340_lines():
    """Phantom's Step 8 exit, from qdt's side (ADR 0087): an adapter, not a model. The cap was 300
    until the layout rename (ADR 0089) took it to 311, and 320 until the starting levels and the
    dynamics option (ADR 0090) took it to 337."""
    import pathlib

    import qdt_sim

    src = pathlib.Path(qdt_sim.__file__).parent
    modules = sorted(p.name for p in src.glob("*.py"))
    assert modules == ["__init__.py", "device.py", "scenarios.py"]
    assert sum(len(p.read_text(encoding="utf-8").splitlines()) for p in src.glob("*.py")) < 340


def test_layout_is_phantoms_knowable_layout_with_each_gate_on_its_stand_channel():
    """ADR 0089: the Device widget's layout is Phantom's, renamed; every gate's channel is a stand DC
    channel, and the layout says where it came from."""
    from qdt_sim.scenarios import DEVICES, default_stand, layout, load_device

    for name in DEVICES:
        drawn = layout(name)
        known = load_device(name).knowable().layout
        assert [(g.name, g.role, [list(p) for p in g.polygon_nm]) for g in drawn.gates] == [
            (g["name"], g["role"], [list(p) for p in g["polygon_nm"]]) for g in known["gates"]
        ]
        assert drawn.material == known["material"] == "SiGe"
        assert list(drawn.channel_nm) == list(known["channel_nm"])
        assert list(drawn.sensor_nm) == list(known["sensor_nm"])
        assert drawn.source == f"Phantom 0.4.0, device file {name}"
        logical = {c.logical: c for c in default_stand().channels}
        for g in drawn.gates:
            assert logical[g.channel].quantity == "voltage"
            assert logical[g.channel].channel == g.name
