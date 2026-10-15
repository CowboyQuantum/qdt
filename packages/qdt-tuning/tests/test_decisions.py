"""The decision rules are pure and reproducible: a result in, a verdict out, every parameter in the rule."""

from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_schemas.data import Annotation
from qdt_schemas.modeling import AnalysisResult, DecisionRule, Estimate, FitModel
from qdt_tuning import (
    RULES,
    apply,
    sensor_operating_point,
    straightened,
    virtual_gate_matrix,
    virtual_gates,
)
from qdt_tuning.decisions import (
    SENSOR_OPERATING_POINT_NAME,
    STRAIGHTENED_NAME,
    VIRTUAL_GATES_NAME,
    decision_rule,
    rule_defaults,
)


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


def test_straightened_accepts_axis_aligned_transitions_and_rejects_cross_talk():
    aligned = straightened(result_with(((71.5, -0.5), (0.3, 68.0))))
    assert aligned.status == "accepted"
    assert aligned.outputs["residual_a"] == pytest.approx(-0.5 / 71.5)
    assert aligned.outputs["residual_b"] == pytest.approx(0.3 / 68.0)
    assert aligned.outputs["l_11"] == 71.5 and aligned.outputs["l_22"] == 68.0
    skewed = straightened(result_with(LATTICE))
    assert skewed.status == "rejected" and "residual" in skewed.message and skewed.outputs == {}
    assert straightened(result_with(LATTICE), max_residual_ratio=0.3).status == "accepted"
    assert straightened(result_with(LATTICE, status="failed", message="x")).status == "failed"
    assert (
        apply(decision_rule(STRAIGHTENED_NAME), result_with(((71.5, -0.5), (0.3, 68.0)))).status
        == "accepted"
    )
    d = virtual_gates(result_with(LATTICE))
    assert d.outputs["c_21"] == pytest.approx(d.outputs["m_21"] / d.outputs["m_11"])
    assert d.outputs["c_12"] == pytest.approx(d.outputs["m_12"] / d.outputs["m_22"])


def diamonds_result(peaks=(-0.06, 0.19), period=0.25, charging=1e-3, status="ok", message=""):
    method = FitModel(name="qdt_analysis.diamonds.detect_diamonds", version="1", parameters={})
    markers = tuple(
        Annotation(
            annotation_id=f"p{k}",
            dataset_id="d",
            kind="marker",
            coords=("SG", "V_sd"),
            points=((g, 0.0),),
            label=f"g{k}",
        )
        for k, g in enumerate(peaks)
    )
    return AnalysisResult(
        result_id="ab" * 16,
        record_id="cd" * 16,
        dataset_id="d",
        method=method,
        method_sha256=method.content_sha256(),
        status=status,
        message=message,
        estimates=(
            Estimate(name="period", value=period, unit="V"),
            Estimate(name="charging_energy", value=charging, unit="eV"),
            Estimate(name="lever_arm", value=charging / period, unit="eV/V"),
        )
        if status == "ok"
        else (),
        annotations=markers if status == "ok" else (),
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )


def test_sensor_operating_point_parks_the_gate_on_the_flank_of_the_nearest_peak():
    d = sensor_operating_point(diamonds_result())
    assert d.status == "accepted" and "of 2" in d.message
    assert d.outputs["sg_peak_v"] == -0.06 and d.outputs["sg_operating_v"] == pytest.approx(-0.04)
    assert d.outputs["period"] == 0.25 and d.outputs["lever_arm"] == pytest.approx(4e-3)
    far = sensor_operating_point(diamonds_result(), near_v=0.15)
    assert far.outputs["sg_peak_v"] == 0.19 and far.outputs["sg_operating_v"] == pytest.approx(0.21)
    assert (
        sensor_operating_point(diamonds_result(), flank_offset_v=0.0).outputs["sg_operating_v"]
        == -0.06
    )
    assert sensor_operating_point(diamonds_result(peaks=())).status == "failed"
    assert (
        sensor_operating_point(diamonds_result(status="failed", message="no diamond")).status
        == "failed"
    )
    assert sensor_operating_point(diamonds_result(period=-1.0)).status == "rejected"
    assert sensor_operating_point(diamonds_result(), flank_offset_v=0.3).status == "rejected"
    rule = decision_rule(SENSOR_OPERATING_POINT_NAME, near_v=0.15)
    assert rule.parameters == {"flank_offset_v": 0.02, "near_v": 0.15}
    assert apply(rule, diamonds_result()).outputs["sg_peak_v"] == 0.19
    assert set(RULES) == {VIRTUAL_GATES_NAME, STRAIGHTENED_NAME, SENSOR_OPERATING_POINT_NAME}
