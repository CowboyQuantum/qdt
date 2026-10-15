"""Calibration nodes against the simulator (ADR 0048, 0049): one node runs and decides; a tune-up chains
nodes through their bound inputs; committed outcomes are reproduced and agree with the model's truth;
and the outcomes a node gives when its method or its stand fails."""

import pathlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.modeling import CalibrationNode, SimResult, SimScenario
from qdt_server.tuning import run_node, run_tuneup
from qdt_sim.scenarios import DEVICE_ID, default_stand, device_for, lattice_truth
from qdt_tuning import charge_lattice, virtual_gate_matrix, virtual_lattice

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

NodeBuilders = Sequence[Callable[[], CalibrationNode]]
SCENARIOS: dict[str, tuple[SimScenario, NodeBuilders]] = {
    "charge_lattice_default": (DEFAULT, [lambda: charge_lattice(instrument=DEVICE_ID)]),
    "charge_lattice_quiet": (QUIET, [lambda: charge_lattice(instrument=DEVICE_ID)]),
    "virtual_lattice_default": (
        DEFAULT,
        [
            lambda: charge_lattice(instrument=DEVICE_ID),
            lambda: virtual_lattice(instrument=DEVICE_ID),
        ],
    ),
    "virtual_lattice_quiet": (
        QUIET,
        [
            lambda: charge_lattice(instrument=DEVICE_ID),
            lambda: virtual_lattice(instrument=DEVICE_ID),
        ],
    ),
}
"""Fixture name → (scenario, the tune-up's nodes in order); the fixture is the last node's outcome.
`scripts/make_tuning_fixtures.py` writes one file each."""


def truth_for(scenario: SimScenario, node_id: str) -> dict[str, float]:
    """The model's values for the node's decided quantities, by the node's output names."""
    lattice = lattice_truth(scenario)
    L = np.array([[lattice["l_11"], lattice["l_12"]], [lattice["l_21"], lattice["l_22"]]])
    M = virtual_gate_matrix(L)
    if node_id == "charge-lattice":
        return (
            lattice
            | {f"m_{i + 1}{j + 1}": float(M[i, j]) for i in range(2) for j in range(2)}
            | {"c_21": float(M[1, 0] / M[0, 0]), "c_12": float(M[0, 1] / M[1, 1])}
        )
    if node_id == "virtual-lattice":
        # in virtual coordinates the lattice is L · C, diagonal when M is right
        C = np.array([[1.0, M[0, 1] / M[1, 1]], [M[1, 0] / M[0, 0], 1.0]])
        LC = L @ C
        return {
            "residual_a": float(LC[0, 1] / LC[0, 0]),
            "residual_b": float(LC[1, 0] / LC[1, 1]),
            "l_11": float(LC[0, 0]),
            "l_22": float(LC[1, 1]),
        }
    raise KeyError(node_id)


def registry_for(root: pathlib.Path) -> Registry:
    registry = Registry(root / "registry")
    registry.register_device(
        DeviceRecord(
            device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
        )
    )
    return registry


def run_scenario(scenario: SimScenario, builders: NodeBuilders, root: pathlib.Path):
    """The tune-up's outcomes; the last node's outcome, result and truth are the fixture's."""
    registry = registry_for(root)
    nodes = [b() for b in builders]
    outcomes = run_tuneup(
        nodes,
        default_stand(),
        {DEVICE_ID: device_for(scenario)},
        registry,
        root / "outbox",
        device_id=DEVICE_ID,
        scenario_id=scenario.scenario_id,
    )
    last = outcomes[-1]
    result = registry.result(last.result_id) if last.result_id else None
    return outcomes, result, truth_for(scenario, nodes[-1].node_id)


TOLERANCES = {
    # name → (relative, absolute) against the model's truth, per decided quantity
    "l_11": (0.01, 0.0),
    "l_22": (0.01, 0.0),
    "l_12": (0.04, 0.0),
    "l_21": (0.04, 0.0),
    "m_11": (0.0, 0.01),
    "m_12": (0.0, 0.01),
    "m_21": (0.0, 0.01),
    "m_22": (0.0, 0.01),
    "c_21": (0.0, 0.01),
    "c_12": (0.0, 0.01),
    "residual_a": (0.0, 0.02),
    "residual_b": (0.0, 0.02),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_tuneup_reproduces_its_committed_outcome_and_the_models_truth(name, tmp_path):
    scenario, builders = SCENARIOS[name]
    fixture = SimResult.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    nodes = [b() for b in builders]
    assert fixture.scenario == scenario and fixture.node_id == nodes[-1].node_id
    outcomes, result, truth = run_scenario(scenario, builders, tmp_path)
    assert [o.node_id for o in outcomes] == [n.node_id for n in nodes]
    assert all(o.status == "accepted" for o in outcomes), [(o.node_id, o.message) for o in outcomes]
    last = outcomes[-1]
    assert last.scenario_id == scenario.scenario_id and result is not None
    # the same scenario decides the same numbers (the simulator is seeded; the method is deterministic)
    assert set(last.outputs) == set(fixture.outcome.outputs)
    for k, v in fixture.outcome.outputs.items():
        assert last.outputs[k] == pytest.approx(v, rel=1e-6), k
    assert {e.name: e.value for e in result.estimates} == pytest.approx(
        {e.name: e.value for e in fixture.estimates}, rel=1e-6
    )
    # and they agree with the model
    assert fixture.truth == pytest.approx(truth, rel=1e-9)
    for k, v in truth.items():
        rel, absolute = TOLERANCES[k]
        assert last.outputs[k] == pytest.approx(v, rel=rel, abs=absolute), (k, last.outputs[k], v)
    # the record and the result are in the registry, with the node's method as the result's provenance
    registry = Registry(tmp_path / "registry")
    assert registry.get(last.record_id).definition_name == nodes[-1].definition.name
    assert registry.result(last.result_id).method == nodes[-1].method


def test_the_virtual_lattice_straightens_what_the_charge_lattice_found(tmp_path):
    """The DAG edge in one picture: cross ratios of ≈ 0.2 in real gates, within 0.01 of zero in the
    virtual gates built from the first node's coefficients."""
    outcomes, _, _ = run_scenario(QUIET, SCENARIOS["virtual_lattice_quiet"][1], tmp_path)
    first, second = outcomes
    assert first.outputs["l_12"] / first.outputs["l_11"] > 0.15
    assert abs(second.outputs["residual_a"]) < 0.01 and abs(second.outputs["residual_b"]) < 0.01
    bound = Registry(tmp_path / "registry").get(second.record_id)
    assert bound.definition_name == "virtual-gate lattice"


def test_a_tuneup_stops_at_the_first_node_that_is_not_accepted(tmp_path):
    """A charge-lattice node whose rule cannot accept (an impossible cross-ratio limit): the second
    node is not run, and its missing input is the reason the tune-up ends there."""
    registry = registry_for(tmp_path)
    strict = charge_lattice(instrument=DEVICE_ID, max_cross_ratio=0.01)
    outcomes = run_tuneup(
        [strict, virtual_lattice(instrument=DEVICE_ID)],
        default_stand(),
        {DEVICE_ID: device_for(QUIET)},
        registry,
        tmp_path / "outbox",
        device_id=DEVICE_ID,
    )
    assert [o.status for o in outcomes] == ["rejected"]
    assert "cross-capacitance" in outcomes[0].message
    with pytest.raises(ValueError, match="not run before it"):
        run_tuneup(
            [virtual_lattice(instrument=DEVICE_ID)],
            default_stand(),
            {},
            registry,
            tmp_path / "outbox",
            device_id=DEVICE_ID,
        )


def test_a_window_without_a_lattice_is_a_failed_outcome_with_its_record_kept(tmp_path):
    """The empty-dot corner with the default noise: no transitions, so the method fails; the outcome says
    so, names the record and the (failed) result, and carries no outputs. (With noise off the map is
    nearly constant and the method reports a degenerate lattice as `ok`: a method weakness, STATUS.md.)"""
    registry = registry_for(tmp_path)
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
    node = charge_lattice(instrument=DEVICE_ID)
    node = node.model_copy(
        update={"method": node.method.model_copy(update={"name": "qdt_analysis.nope"})}
    )
    with pytest.raises(KeyError, match="no method"):
        run_node(
            node, default_stand(), {}, Registry(tmp_path / "r"), tmp_path / "o", device_id=DEVICE_ID
        )


def test_a_stand_that_cannot_run_the_node_is_a_failed_outcome(tmp_path):
    registry = registry_for(tmp_path)
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
