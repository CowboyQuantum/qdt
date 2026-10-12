"""The committed scenario fixture: the default noisy device reproduces it within tolerance."""

import pathlib

import numpy as np

from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.stream import assemble
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, stability_fixture

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "stability_24x32.npy"
SEED = 7


def run_fixture() -> np.ndarray:
    plan = compile_sweep(stability_fixture(), default_stand(), {"simulated": SimulatedEmitter()})
    source = Executor(plan, {DEVICE_ID: default_device(seed=SEED)}).run()
    return assemble(plan.dataset, source.frames())["I_sensor"].values


def test_scenario_reproduces_committed_fixture():
    expected = np.load(FIXTURE)
    got = run_fixture()
    assert got.shape == expected.shape == (24, 32)
    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-21)


def test_fixture_shows_charge_transitions():
    """Sanity on the physics the fixture captures: the map is not flat and has sharp features."""
    x = np.load(FIXTURE)
    assert x.std() > 0.05 * x.mean()
    jumps = np.abs(np.diff(x, axis=1))
    assert jumps.max() > 5 * np.median(jumps)
