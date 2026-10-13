"""Injection–recovery against `SimulatedDevice` (Step 4 L0): the dot model knows the true transition
lines (`DoubleDotModel.transition_map`), and the `ScenarioRef` on the result regenerates them."""

import numpy as np
import pytest

from qdt_analysis import charge_transitions, recovery
from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.stream import assemble
from qdt_schemas.modeling import ScenarioRef
from qdt_sim.scenarios import DEVICE_ID, resolve

WINDOW = {"n_outer": 64, "n_inner": 64, "p1_start": -0.02, "p1_stop": 0.06, "p2_start": -0.02, "p2_stop": 0.06}


def run(ref: ScenarioRef):
    """Run the scenario the ref names; returns (dataset, arrays, truth mask of dot-addition lines)."""
    scenario = resolve(ref)
    plan = compile_sweep(scenario.definition, scenario.stand, {"simulated": SimulatedEmitter()})
    xds = assemble(plan.dataset, Executor(plan, {DEVICE_ID: scenario.device}).run().frames())
    arrays = {"I_sensor": xds["I_sensor"].values}
    p1, p2 = xds["P1"].values, xds["P2"].values
    v = np.stack([*np.meshgrid(p1, p2, indexing="ij"), np.zeros((p1.size, p2.size))], axis=-1)
    truth = scenario.device.model.transition_map(v)
    return plan.dataset, arrays, np.isin(truth, (1, 2))


@pytest.fixture(scope="module")
def clean():
    ref = ScenarioRef(
        kind="simulation",
        name="stability",
        seed=0,
        parameters={**WINDOW, "noise": False, "sample_charge": False},
    )
    return ref, *run(ref)


@pytest.fixture(scope="module")
def noisy():
    ref = ScenarioRef(kind="simulation", name="stability", seed=11, parameters=WINDOW)
    return ref, *run(ref)


def test_noise_free_device_lines_are_recovered(clean):
    ref, dataset, arrays, truth = clean
    result = charge_transitions(dataset, arrays, ref)
    r = recovery(result, dataset, arrays, truth, tolerance=1.5)
    assert r.precision > 0.95 and r.recall > 0.9, r
    assert result.summary["n_families"] == 2
    assert result.measurement.dataset_id == dataset.dataset_id
    assert result.measurement.variable == "I_sensor"


def test_noisy_device_lines_are_recovered(noisy):
    ref, dataset, arrays, truth = noisy
    result = charge_transitions(dataset, arrays, ref)
    r = recovery(result, dataset, arrays, truth, tolerance=2.0)
    assert r.precision > 0.85 and r.recall > 0.8, r


def test_scenario_ref_on_the_result_regenerates_the_truth(clean):
    ref, dataset, arrays, truth = clean
    result = charge_transitions(dataset, arrays, ref)
    again = resolve(result.scenario)
    plan = compile_sweep(again.definition, again.stand, {"simulated": SimulatedEmitter()})
    assert plan.dataset.coords == dataset.coords
    p1, p2 = np.linspace(-0.02, 0.06, 64), np.linspace(-0.02, 0.06, 64)
    v = np.stack([*np.meshgrid(p1, p2, indexing="ij"), np.zeros((64, 64))], axis=-1)
    np.testing.assert_array_equal(np.isin(again.device.model.transition_map(v), (1, 2)), truth)


def test_annotations_sit_on_the_dataset_coordinates(clean):
    ref, dataset, arrays, _ = clean
    result = charge_transitions(dataset, arrays, ref)
    assert result.annotations, "expected transition lines"
    for a in result.annotations:
        dataset.check_annotation(a)
        assert a.coords == ("P1", "P2")
        assert all(-0.02 <= p[0] <= 0.06 and -0.02 <= p[1] <= 0.06 for p in a.points)
