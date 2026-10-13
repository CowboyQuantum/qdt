"""The committed scenario fixture: the default noisy device reproduces it within tolerance."""

import pathlib

import numpy as np
import pytest

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


def test_scenario_ref_resolves_to_the_fixture_sweep_and_a_seeded_device():
    from qdt_schemas.modeling import ScenarioRef
    from qdt_sim.scenarios import resolve

    ref = ScenarioRef(kind="simulation", name="stability_fixture", seed=SEED)
    scenario = resolve(ref)
    assert scenario.definition == stability_fixture()
    assert scenario.stand == default_stand()
    plan = compile_sweep(scenario.definition, scenario.stand, {"simulated": SimulatedEmitter()})
    got = assemble(plan.dataset, Executor(plan, {DEVICE_ID: scenario.device}).run().frames())
    np.testing.assert_allclose(got["I_sensor"].values, np.load(FIXTURE), rtol=1e-9, atol=1e-21)


def test_scenario_ref_parameters_cover_ranges_and_device_options():
    from qdt_schemas.modeling import ScenarioRef
    from qdt_sim.scenarios import resolve, stability

    ref = ScenarioRef(
        kind="simulation",
        name="stability",
        seed=0,
        parameters={
            "n_outer": 16,
            "n_inner": 8,
            "p1_start": -0.02,
            "p1_stop": 0.06,
            "noise": False,
            "sample_charge": False,
        },
    )
    scenario = resolve(ref)
    assert scenario.definition == stability(16, 8, p1=(-0.02, 0.06))
    assert scenario.device.sample_charge is False
    with pytest.raises(ValueError, match="unknown scenario"):
        resolve(ref.model_copy(update={"name": "nope"}))
    with pytest.raises(ValueError, match="'simulation'"):
        resolve(ref.model_copy(update={"kind": "synthetic"}))
    with pytest.raises(ValueError, match="_start and _stop"):
        resolve(ref.model_copy(update={"parameters": {"p1_start": 0.0}}))
