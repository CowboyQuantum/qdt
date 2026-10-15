"""The decision rules are pure and reproducible: a result in, a verdict out, every parameter in the rule."""

from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_schemas.modeling import AnalysisResult, DecisionRule, Estimate, FitModel
from qdt_tuning import RULES, apply, virtual_gate_matrix, virtual_gates
from qdt_tuning.decisions import VIRTUAL_GATES_NAME, decision_rule, rule_defaults


def result_with(lattice, status="ok", message="") -> AnalysisResult:
    method = FitModel(
        name="qdt_analysis.transitions.detect_transitions", version="1", parameters={}
    )
    (a_row, a_col), (b_row, b_col) = lattice
    estimates = (
        Estimate(name="a_per_volt_row", value=a_row, unit="1/V"),
        Estimate(name="a_per_volt_col", value=a_col, unit="1/V"),
        Estimate(name="b_per_volt_row", value=b_row, unit="1/V"),
        Estimate(name="b_per_volt_col", value=b_col, unit="1/V"),
    )
    return AnalysisResult(
        result_id="ab" * 16,
        record_id="cd" * 16,
        dataset_id="d",
        method=method,
        method_sha256=method.content_sha256(),
        status=status,
        message=message,
        estimates=estimates if status == "ok" else (),
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )


LATTICE = ((74.9, 15.6), (15.6, 71.8))  # the default model's C_gate / e for (P1, P2), roughly


def test_virtual_gate_matrix_removes_the_cross_talk_and_keeps_each_gates_lever_arm():
    lattice = np.array(LATTICE)
    m = virtual_gate_matrix(lattice)
    # moving virtual gate j by one volt adds L[j, j] electrons' worth to dot j and nothing to the other
    np.testing.assert_allclose(lattice @ m, np.diag(np.diag(lattice)), atol=1e-12)
    np.testing.assert_allclose(virtual_gate_matrix(np.diag([70.0, 80.0])), np.eye(2))
    with pytest.raises(ValueError, match="2 × 2"):
        virtual_gate_matrix(np.ones((3, 3)))


def test_accepts_a_plausible_lattice_and_decides_the_matrix():
    d = virtual_gates(result_with(LATTICE))
    assert d.status == "accepted" and "condition" in d.message
    assert d.outputs["l_11"] == 74.9 and d.outputs["l_12"] == 15.6
    m = virtual_gate_matrix(np.array(LATTICE))
    for i in range(2):
        for j in range(2):
            assert d.outputs[f"m_{i + 1}{j + 1}"] == pytest.approx(m[i, j])


def test_rejects_what_is_not_a_double_dot_lattice():
    assert (
        virtual_gates(result_with(((74.9, 60.0), (15.6, 71.8)))).status == "rejected"
    )  # ratio 0.8
    assert "cross-capacitance" in virtual_gates(result_with(((74.9, 60.0), (15.6, 71.8)))).message
    assert virtual_gates(result_with(((-74.9, 15.6), (15.6, 71.8)))).status == "rejected"
    assert (
        virtual_gates(result_with(((74.9, -1.0), (15.6, 71.8)))).status == "rejected"
    )  # ratio < 0
    # nearly parallel lattice vectors: ratios inside the limit, condition number ≈ 140
    ill = virtual_gates(result_with(((70.0, 69.0), (69.0, 70.0))), max_cross_ratio=1.0)
    assert ill.status == "rejected" and "ill-conditioned" in ill.message
    assert (
        virtual_gates(result_with(((74.9, 60.0), (15.6, 71.8))), max_cross_ratio=0.9).status
        == "accepted"
    )
    assert virtual_gates(result_with(LATTICE)).outputs and not ill.outputs


def test_a_failed_result_is_a_failed_decision_not_a_rejection():
    d = virtual_gates(result_with(LATTICE, status="failed", message="no lattice peaks"))
    assert d.status == "failed" and "no lattice peaks" in d.message and d.outputs == {}
    bare = result_with(LATTICE).model_copy(
        update={"estimates": (Estimate(name="period", value=1.0, unit="V"),)}
    )
    assert virtual_gates(bare).status == "failed"


def test_rules_are_applied_by_their_data_and_every_parameter_is_carried():
    rule = decision_rule(VIRTUAL_GATES_NAME)
    assert (
        rule.parameters
        == rule_defaults(VIRTUAL_GATES_NAME)
        == {"max_cross_ratio": 0.6, "max_condition": 10.0}
    )
    assert apply(rule, result_with(LATTICE)).status == "accepted"
    strict = decision_rule(VIRTUAL_GATES_NAME, max_cross_ratio=0.1)
    assert apply(strict, result_with(LATTICE)).status == "rejected"
    with pytest.raises(ValueError, match="no parameters"):
        decision_rule(VIRTUAL_GATES_NAME, nope=1)
    with pytest.raises(KeyError):
        decision_rule("qdt_tuning.decisions.nope")
    with pytest.raises(KeyError):
        apply(DecisionRule(name="x", version="1"), result_with(LATTICE))
    with pytest.raises(ValueError, match="version"):
        apply(rule.model_copy(update={"version": "0"}), result_with(LATTICE))
    with pytest.raises(ValueError, match="takes"):
        apply(
            DecisionRule(name=VIRTUAL_GATES_NAME, version="1", parameters={"max_cross_ratio": 0.6}),
            result_with(LATTICE),
        )
    assert set(RULES) == {VIRTUAL_GATES_NAME}
