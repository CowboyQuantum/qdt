"""The first calibration node against the simulator (ADR 0048): run, decide, reproduce the committed
outcome, agree with the model's truth; and the outcomes a node gives when its method fails."""

import pathlib
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.modeling import SimResult, SimScenario
from qdt_server.tuning import run_node
from qdt_sim.scenarios import DEVICE_ID, default_stand, device_for, lattice_truth
from qdt_tuning import charge_lattice, virtual_gate_matrix

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

DEFAULT = SimScenario(
    scenario_id="default-occupied-window",
    description="the default double dot with its default noise, seed 1; the charge-lattice node's window",
    seed=1,
)
QUIET = SimScenario(
    scenario_id="default-quiet",
    description="the default double dot, noise off",
    seed=0,
    noise=False,
)
SCENARIOS = {
    "charge_lattice_default": (DEFAULT, lambda: charge_lattice(instrument=DEVICE_ID)),
    "charge_lattice_quiet": (QUIET, lambda: charge_lattice(instrument=DEVICE_ID)),
}
"""Fixture name → (scenario, node builder); `scripts/make_tuning_fixtures.py` writes one file each."""


def truth_for(scenario: SimScenario) -> dict[str, float]:
    """The model's lattice and the virtual-gate matrix it implies, by the node's output names."""
    lattice = lattice_truth(scenario)
    m = virtual_gate_matrix(
        np.array([[lattice["l_11"], lattice["l_12"]], [lattice["l_21"], lattice["l_22"]]])
    )
    return lattice | {f"m_{i + 1}{j + 1}": float(m[i, j]) for i in range(2) for j in range(2)}


def run_scenario(scenario: SimScenario, node_builder, root: pathlib.Path):
    registry = Registry(root / "registry")
    registry.register_device(
        DeviceRecord(
            device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
        )
    )
    node = node_builder()
    outcome, result = run_node(
        node,
        default_stand(),
        {DEVICE_ID: device_for(scenario)},
        registry,
        root / "outbox",
        device_id=DEVICE_ID,
        scenario_id=scenario.scenario_id,
    )
    return outcome, result, truth_for(scenario)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_node_reproduces_its_committed_outcome_and_the_models_truth(name, tmp_path):
    scenario, builder = SCENARIOS[name]
    fixture = SimResult.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert fixture.scenario == scenario and fixture.node_id == builder().node_id
    outcome, result, truth = run_scenario(scenario, builder, tmp_path)
    assert outcome.status == fixture.outcome.status == "accepted", outcome.message
    assert outcome.scenario_id == scenario.scenario_id
    assert outcome.record_id and outcome.result_id and result is not None
    # the same scenario decides the same numbers (the simulator is seeded; the method is deterministic)
    assert set(outcome.outputs) == set(fixture.outcome.outputs)
    for k, v in fixture.outcome.outputs.items():
        assert outcome.outputs[k] == pytest.approx(v, rel=1e-6), k
    assert {e.name: e.value for e in result.estimates} == pytest.approx(
        {e.name: e.value for e in fixture.estimates}, rel=1e-6
    )
    # and they agree with the model: lever arms within 1 %, cross terms within 4 %, the matrix within 0.01
    assert fixture.truth == truth
    for k in ("l_11", "l_22"):
        assert outcome.outputs[k] == pytest.approx(truth[k], rel=0.01), k
    for k in ("l_12", "l_21"):
        assert outcome.outputs[k] == pytest.approx(truth[k], rel=0.04), k
    for k in ("m_11", "m_12", "m_21", "m_22"):
        assert outcome.outputs[k] == pytest.approx(truth[k], abs=0.01), k
    # the record and the result are in the registry, with the node's method as the result's provenance
    record = Registry(tmp_path / "registry").get(outcome.record_id)
    assert record.definition_name == "charge lattice"
    stored = Registry(tmp_path / "registry").result(outcome.result_id)
    assert stored.method == builder().method and stored.status == "ok"


def test_a_window_without_a_lattice_is_a_failed_outcome_with_its_record_kept(tmp_path):
    """The empty-dot corner with the default noise: no transitions, so the method fails; the outcome says
    so, names the record and the (failed) result, and carries no outputs. (With noise off the map is
    nearly constant and the method reports a degenerate lattice as `ok`: a method weakness, STATUS.md.)"""
    registry = Registry(tmp_path / "registry")
    registry.register_device(
        DeviceRecord(
            device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
        )
    )
    node = charge_lattice(instrument=DEVICE_ID, p1=(-0.3, -0.25), p2=(-0.3, -0.25), n=24)
    outcome, result = run_node(
        node,
        default_stand(),
        {DEVICE_ID: device_for(DEFAULT)},
        registry,
        tmp_path / "outbox",
        device_id=DEVICE_ID,
    )
    assert outcome.status == "failed" and outcome.outputs == {}, outcome.message
    assert (
        outcome.record_id and outcome.result_id and result is not None and result.status == "failed"
    )
    assert "the method failed" in outcome.message


def test_a_node_with_an_unknown_method_is_a_definition_error(tmp_path):
    node = charge_lattice(instrument=DEVICE_ID).model_copy(
        update={
            "method": charge_lattice(instrument=DEVICE_ID).method.model_copy(
                update={"name": "qdt_analysis.nope"}
            )
        }
    )
    with pytest.raises(KeyError, match="no method"):
        run_node(
            node, default_stand(), {}, Registry(tmp_path / "r"), tmp_path / "o", device_id=DEVICE_ID
        )


def test_a_stand_that_cannot_run_the_node_is_a_failed_outcome(tmp_path):
    registry = Registry(tmp_path / "registry")
    registry.register_device(
        DeviceRecord(
            device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
        )
    )
    node = charge_lattice(instrument="nope")  # no such sequencer on the stand
    outcome, result = run_node(
        node,
        default_stand(),
        {DEVICE_ID: device_for(QUIET)},
        registry,
        tmp_path / "outbox",
        device_id=DEVICE_ID,
    )
    assert outcome.status == "failed" and outcome.record_id is None and result is None
    assert "nope" in outcome.message
