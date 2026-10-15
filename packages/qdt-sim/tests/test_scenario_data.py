"""`SimScenario` as data (ADR 0048): the simulator realizes it and derives the truth from the model."""

import dataclasses

import numpy as np
import pytest

from qdt_schemas.modeling import SimScenario
from qdt_sim.scenarios import default_model, device_for, lattice_truth, model_for


def same_model(a, b) -> bool:
    """Field-wise equality of two models (their matrices are numpy arrays, so `==` is ambiguous)."""
    for f in dataclasses.fields(a):
        x, y = getattr(a, f.name), getattr(b, f.name)
        if isinstance(x, np.ndarray):
            if not np.array_equal(x, y):
                return False
        elif x != y:
            return False
    return True


def test_a_scenario_overrides_scalars_of_the_default_model_only():
    plain = SimScenario(scenario_id="plain")
    assert same_model(model_for(plain), default_model())
    cold = SimScenario(scenario_id="cold", model={"sensor_width_v": 0.01, "temperature_k": 0.05})
    m = model_for(cold)
    assert m.sensor_width_v == 0.01 and m.temperature_k == 0.05
    assert same_model(
        m, dataclasses.replace(default_model(), sensor_width_v=0.01, temperature_k=0.05)
    )
    with pytest.raises(ValueError, match="unknown fields"):
        model_for(SimScenario(scenario_id="x", model={"nope": 1.0}))
    with pytest.raises(TypeError, match="not a scalar"):
        model_for(SimScenario(scenario_id="x", model={"c_gate": 1.0}))


def test_a_realized_scenario_is_a_seeded_device_and_its_truth_is_the_models_lattice():
    a = device_for(SimScenario(scenario_id="s", seed=4))
    b = device_for(SimScenario(scenario_id="s", seed=4))
    assert a.sense("sensor") == b.sense("sensor")  # same seed, same draw
    quiet = device_for(SimScenario(scenario_id="q", seed=4, noise=False))
    assert quiet.sense("sensor") == quiet.sense("sensor")
    truth = lattice_truth(SimScenario(scenario_id="s"))
    lattice = default_model().charge_lattice("P1", "P2")
    assert set(truth) == {"l_11", "l_12", "l_21", "l_22"}
    np.testing.assert_allclose(
        [[truth["l_11"], truth["l_12"]], [truth["l_21"], truth["l_22"]]], lattice
    )
