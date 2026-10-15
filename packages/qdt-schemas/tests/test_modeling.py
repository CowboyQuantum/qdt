"""Modeling slice (ADR 0029): an AnalysisResult always carries both halves of its provenance."""

import json
import pathlib

import pytest
from pydantic import ValidationError

from qdt_schemas.modeling import AnalysisResult

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "AnalysisResult" / "v1.json"


def data() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("missing", ["record_id", "method", "method_sha256"])
def test_missing_either_half_of_the_provenance_fails(missing):
    d = data()
    del d[missing]
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(d)


def test_method_hash_must_match_the_method():
    d = data()
    d["method"]["parameters"]["smooth_px"] = 2.0
    with pytest.raises(ValidationError, match="method_sha256"):
        AnalysisResult.model_validate(d)


def test_overlays_decorate_the_analysed_dataset_only():
    d = data()
    d["annotations"][0]["dataset_id"] = "elsewhere"
    with pytest.raises(ValidationError, match="another dataset"):
        AnalysisResult.model_validate(d)


def test_an_ok_result_says_something():
    d = data() | {"estimates": [], "annotations": []}
    with pytest.raises(ValidationError, match="ok result"):
        AnalysisResult.model_validate(d)
    AnalysisResult.model_validate(d | {"status": "failed", "message": "no transitions"})


def test_estimate_names_are_unique():
    d = data()
    d["estimates"] = d["estimates"] * 2
    with pytest.raises(ValidationError, match="unique"):
        AnalysisResult.model_validate(d)


def test_step_6_objects_hold_a_node_its_outcome_and_a_scenario(tmp_path=None):
    """ADR 0048: additive objects beside the frozen three; validators keep an outcome honest."""
    from datetime import UTC, datetime

    import pytest
    from pydantic import ValidationError

    from qdt_schemas.activity import SensedLevel, SweepAxis, SweepDefinition
    from qdt_schemas.modeling import (
        CalibrationNode,
        DecisionRule,
        FitModel,
        NodeOutcome,
        SimResult,
        SimScenario,
    )

    scenario = SimScenario(scenario_id="s", model={"sensor_width_v": 0.01}, seed=3)
    assert scenario.noise is True and scenario.model["sensor_width_v"] == 0.01
    definition = SweepDefinition(
        name="d",
        axes=(SweepAxis(name="g", channel="g", start=0, stop=1, num=4),),
        sensed=(SensedLevel(name="I", channel="s"),),
    )
    node = CalibrationNode(
        node_id="n",
        definition=definition,
        method=FitModel(name="m", version="1", parameters={"k": 1}),
        decision=DecisionRule(name="r", version="1", parameters={"t": 0.5}),
        depends_on=("a", "b"),
    )
    assert node.depends_on == ("a", "b")
    with pytest.raises(ValidationError, match="once"):
        node.model_copy(update={"depends_on": ("a", "a")}).model_validate(
            node.model_dump() | {"depends_on": ["a", "a"]}
        )
    with pytest.raises(ValidationError, match="itself"):
        CalibrationNode.model_validate(node.model_dump() | {"depends_on": ["n"]})
    now = datetime(2026, 10, 15, tzinfo=UTC)
    accepted = NodeOutcome(
        outcome_id="ab" * 16,
        node_id="n",
        record_id="cd" * 16,
        result_id="ef" * 16,
        status="accepted",
        outputs={"m_11": 1.0},
        created_at=now,
    )
    assert accepted.scenario_id is None and accepted.outputs == {"m_11": 1.0}
    with pytest.raises(ValidationError, match="names its record and result"):
        NodeOutcome(
            outcome_id="ab" * 16, node_id="n", status="accepted", outputs={"x": 1.0}, created_at=now
        )
    with pytest.raises(ValidationError, match="only an accepted"):
        NodeOutcome(
            outcome_id="ab" * 16, node_id="n", status="rejected", outputs={"x": 1.0}, created_at=now
        )
    failed = NodeOutcome(
        outcome_id="ab" * 16, node_id="n", status="failed", message="no lattice", created_at=now
    )
    assert failed.record_id is None and failed.outputs == {}
    fixture = SimResult(
        scenario=scenario, node_id="n", outcome=accepted, truth={"m_11": 1.0}, created_at=now
    )
    assert SimResult.model_validate_json(fixture.model_dump_json()) == fixture
