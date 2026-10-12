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
