"""`SimScenario` as data (ADR 0048, 0088): the simulator loads the scenario's committed device and takes
the truth from Phantom's `Device.truth`, renaming only."""

import numpy as np
import pytest

from qdt_schemas.modeling import SimScenario
from qdt_sim.scenarios import (
    DEVICES,
    device_for,
    lattice_truth,
    load_device,
    sensor_truth,
    start,
)


def scenario(name: str = "two-dot-sige-a", **kwargs) -> SimScenario:
    return SimScenario(scenario_id="s", device=name, device_sha256=DEVICES[name], **kwargs)


def test_a_scenario_loads_its_committed_device_and_refuses_another_hash():
    a, b = device_for(scenario()), device_for(scenario("two-dot-sige-b"))
    assert a.device.seed != b.device.seed and a.device.gate_names == b.device.gate_names
    wrong = SimScenario(
        scenario_id="w", device="two-dot-sige-a", device_sha256=DEVICES["two-dot-sige-b"]
    )
    with pytest.raises(ValueError, match="hashes to"):
        device_for(wrong)


def test_a_realized_scenario_is_a_seeded_run_and_its_truth_is_the_slope_of_phantoms_charge():
    """The lattice truth is the slope of Phantom's gate-induced charge at the start (ADR 0092): since
    Phantom 0.6.0 the dots grow with their occupancy, so at the operating point the honeycomb is 3/2
    as dense as the compiled matrix `Device.truth` still reports (Phantom #75)."""
    a, b = device_for(scenario(seed=4)), device_for(scenario(seed=4))
    assert a.sense("sensor") == b.sense("sensor")  # same noise seed, same draw
    quiet = device_for(scenario(seed=4, noise=False))
    assert np.isfinite(quiet.sense("sensor"))
    truth = lattice_truth(scenario())
    compiled = np.array(load_device().truth(("P1", "P2")).charge_lattice_e_per_v)
    assert set(truth) == {"l_11", "l_12", "l_21", "l_22"}
    lattice = np.array([[truth["l_11"], truth["l_12"]], [truth["l_21"], truth["l_22"]]])
    assert lattice[0, 0] > lattice[0, 1] > 0 and lattice[1, 1] > lattice[1, 0] > 0
    np.testing.assert_allclose(lattice / compiled, 1.5, atol=0.06)


def test_the_sensors_truth_is_phantoms_peak_nearest_the_starting_sensor_gate():
    device = load_device()
    s = device.truth(near_v=start(device)["SG"]).sensor
    t = sensor_truth(scenario())
    assert t == {
        "sg_peak_v": s.peak_v,
        "period": s.period_v,
        "charging_energy": s.charging_energy_ev,
        "lever_arm": s.lever_arm_ev_per_v,
        "sg_width_v": s.width_v,
        "sg_wing_v": s.wing_v,
        "sensitivity_a_per_v": s.sensitivity_a_per_v,
    }
    # one period further up is the next peak; the sensitivity follows the bias in linear response
    above = sensor_truth(scenario(), near_v=s.peak_v + s.period_v)["sg_peak_v"]
    assert above == pytest.approx(s.peak_v + s.period_v, abs=0.05)
    low = sensor_truth(scenario(), bias_v=10e-6)["sensitivity_a_per_v"]
    assert low == pytest.approx(t["sensitivity_a_per_v"] * 10e-6 / 50e-6, rel=0.05)
