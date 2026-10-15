"""Curated decision rules: an `AnalysisResult` in, a `Decision` out (ADR 0048).

A rule is the part of a calibration node that is neither measurement nor analysis: it reads the
estimates a curated method produced and says whether the node is done, and with which numbers the next
node proceeds. Rules are small, named, versioned and parameterized like methods, so an outcome is
reproducible from its `DecisionRule`.
"""

import inspect
from collections.abc import Callable
from typing import NamedTuple

import numpy as np

from qdt_schemas.data import AttrValue
from qdt_schemas.modeling import AnalysisResult, DecisionRule


class Decision(NamedTuple):
    """A rule's verdict: `accepted` with `outputs`, `rejected` with a reason, or `failed` (the result was)."""

    status: str
    message: str
    outputs: dict[str, float]


def virtual_gate_matrix(lattice: np.ndarray) -> np.ndarray:
    """The virtual-gate matrix `M` of a charge lattice `L` (electrons per volt, [dot, gate]).

    Column j of `M` is the real-gate move, in volts, that adds `L[j, j]` electrons' worth of gate charge
    to dot j and none to the other: `M = L⁻¹ · diag(diag(L))`, so a virtual gate has its own gate's
    lever arm and no cross-talk. `M` is the identity when `L` is diagonal.
    """
    lattice = np.asarray(lattice, dtype=float)
    if lattice.shape != (2, 2):
        raise ValueError(f"a two-dot lattice is 2 × 2, got {lattice.shape}")
    return np.linalg.solve(lattice, np.diag(np.diag(lattice)))


VIRTUAL_GATES_NAME = "qdt_tuning.decisions.virtual_gates"
VIRTUAL_GATES_VERSION = "1"


def virtual_gates(
    result: AnalysisResult, *, max_cross_ratio: float = 0.6, max_condition: float = 10.0
) -> Decision:
    """Judge a charge-transitions result (`qdt_analysis.transitions.detect_transitions`): accept when its
    lattice is a plausible double-dot lattice and decide the virtual-gate matrix from it.

    Accepted when the result is `ok`, both diagonal lever arms are positive, both cross-capacitance
    ratios lie in [0, `max_cross_ratio`] and the lattice's condition number is below `max_condition`.
    Outputs: `l_11`, `l_12`, `l_21`, `l_22` (the lattice, electrons per volt, [dot, gate]); `m_11`,
    `m_12`, `m_21`, `m_22` (the virtual-gate matrix); and the compensation coefficients `c_21 = m_21 /
    m_11` (volts of gate 2 per volt of virtual gate 1) and `c_12 = m_12 / m_22`, which a coupled axis
    and an Affine pulse level take directly (ADR 0049).
    """
    if result.status != "ok":
        return Decision("failed", f"the method failed: {result.message}", {})
    try:
        a_row, a_col = (
            result.estimate("a_per_volt_row").value,
            result.estimate("a_per_volt_col").value,
        )
        b_row, b_col = (
            result.estimate("b_per_volt_row").value,
            result.estimate("b_per_volt_col").value,
        )
    except KeyError as e:
        return Decision("failed", f"the result lacks a lattice estimate: {e}", {})
    lattice = np.array([[a_row, a_col], [b_row, b_col]])
    if not (a_row > 0 and b_col > 0):
        return Decision(
            "rejected", f"a lever arm is not positive: diag {a_row:.3g}, {b_col:.3g}", {}
        )
    ratios = (a_col / a_row, b_row / b_col)
    if not all(0.0 <= r <= max_cross_ratio for r in ratios):
        return Decision(
            "rejected",
            f"cross-capacitance ratios {ratios[0]:.3f}, {ratios[1]:.3f} outside [0, {max_cross_ratio}]",
            {},
        )
    condition = float(np.linalg.cond(lattice))
    if not condition < max_condition:
        return Decision(
            "rejected", f"the lattice is ill-conditioned ({condition:.1f} ≥ {max_condition})", {}
        )
    m = virtual_gate_matrix(lattice)
    outputs = {
        "l_11": float(lattice[0, 0]),
        "l_12": float(lattice[0, 1]),
        "l_21": float(lattice[1, 0]),
        "l_22": float(lattice[1, 1]),
        "m_11": float(m[0, 0]),
        "m_12": float(m[0, 1]),
        "m_21": float(m[1, 0]),
        "m_22": float(m[1, 1]),
        "c_21": float(m[1, 0] / m[0, 0]),
        "c_12": float(m[0, 1] / m[1, 1]),
    }
    return Decision(
        "accepted",
        f"lattice condition {condition:.2f}, cross ratios {ratios[0]:.3f} and {ratios[1]:.3f}",
        outputs,
    )


STRAIGHTENED_NAME = "qdt_tuning.decisions.straightened"
STRAIGHTENED_VERSION = "1"


def straightened(result: AnalysisResult, *, max_residual_ratio: float = 0.05) -> Decision:
    """Judge a charge-transitions result taken in virtual gates: accept when the honeycomb is
    axis-aligned, i.e. both residual cross-capacitance ratios are within `max_residual_ratio` of zero.
    Outputs: `residual_a`, `residual_b` (the ratios, signed) and `l_11`, `l_22` (the lever arms in the
    virtual coordinates, electrons per volt)."""
    if result.status != "ok":
        return Decision("failed", f"the method failed: {result.message}", {})
    try:
        a_row, a_col = (
            result.estimate("a_per_volt_row").value,
            result.estimate("a_per_volt_col").value,
        )
        b_row, b_col = (
            result.estimate("b_per_volt_row").value,
            result.estimate("b_per_volt_col").value,
        )
    except KeyError as e:
        return Decision("failed", f"the result lacks a lattice estimate: {e}", {})
    if not (a_row > 0 and b_col > 0):
        return Decision(
            "rejected", f"a lever arm is not positive: diag {a_row:.3g}, {b_col:.3g}", {}
        )
    residual_a, residual_b = a_col / a_row, b_row / b_col
    if max(abs(residual_a), abs(residual_b)) > max_residual_ratio:
        return Decision(
            "rejected",
            f"residual cross ratios {residual_a:+.3f}, {residual_b:+.3f} exceed ±{max_residual_ratio}",
            {},
        )
    return Decision(
        "accepted",
        f"residual cross ratios {residual_a:+.3f}, {residual_b:+.3f}",
        {
            "residual_a": float(residual_a),
            "residual_b": float(residual_b),
            "l_11": float(a_row),
            "l_22": float(b_col),
        },
    )


SENSOR_OPERATING_POINT_NAME = "qdt_tuning.decisions.sensor_operating_point"
SENSOR_OPERATING_POINT_VERSION = "1"


def sensor_operating_point(
    result: AnalysisResult, *, flank_offset_v: float = 0.02, near_v: float = 0.0
) -> Decision:
    """Judge a Coulomb-diamonds result (`qdt_analysis.diamonds.detect_diamonds`, ADR 0030) and decide
    where to park the sensor gate: on the flank of the Coulomb peak (degeneracy point) nearest `near_v`,
    `flank_offset_v` above it, where the sensor's current changes fastest with charge (ADR 0052).

    Accepted when the result is `ok`, it marks at least one degeneracy point and its period and charging
    energy are positive. Outputs: `sg_peak_v` (the chosen peak), `sg_operating_v` (= peak +
    flank_offset_v), `period`, `charging_energy`, `lever_arm`. The offset is a parameter because the
    method does not estimate the peak's width; a peak-width method is the right successor.
    """
    if result.status != "ok":
        return Decision("failed", f"the method failed: {result.message}", {})
    peaks = sorted(
        float(a.points[0][0])
        for a in result.annotations
        if a.kind == "marker" and a.label.startswith("g") and len(a.points[0]) >= 1
    )
    if not peaks:
        return Decision("failed", "the result marks no degeneracy point", {})
    try:
        period = result.estimate("period").value
        charging = result.estimate("charging_energy").value
        lever = result.estimate("lever_arm").value
    except KeyError as e:
        return Decision("failed", f"the result lacks a diamond estimate: {e}", {})
    if not (period > 0 and charging > 0):
        return Decision(
            "rejected",
            f"period {period:.3g} and charging energy {charging:.3g} must be positive",
            {},
        )
    if not 0 <= flank_offset_v < period:
        return Decision(
            "rejected",
            f"flank offset {flank_offset_v:.3g} V must lie within one period ({period:.3g} V)",
            {},
        )
    peak = min(peaks, key=lambda g: abs(g - near_v))
    return Decision(
        "accepted",
        f"peak at {peak:+.4f} V (of {len(peaks)}), operating point {peak + flank_offset_v:+.4f} V",
        {
            "sg_peak_v": peak,
            "sg_operating_v": peak + flank_offset_v,
            "period": float(period),
            "charging_energy": float(charging),
            "lever_arm": float(lever),
        },
    )


Rule = Callable[..., Decision]

RULES: dict[str, tuple[str, Rule]] = {
    VIRTUAL_GATES_NAME: (VIRTUAL_GATES_VERSION, virtual_gates),
    STRAIGHTENED_NAME: (STRAIGHTENED_VERSION, straightened),
    SENSOR_OPERATING_POINT_NAME: (SENSOR_OPERATING_POINT_VERSION, sensor_operating_point),
}
"""Rule name → (version, callable). A rule is applicable through `apply` only if it is here."""


def rule_defaults(name: str) -> dict[str, AttrValue]:
    """Every keyword parameter of rule `name` with its default: what a `DecisionRule` must carry."""
    _, fn = RULES[name]
    return {
        p.name: p.default
        for p in inspect.signature(fn).parameters.values()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    }


def decision_rule(name: str, **parameters: AttrValue) -> DecisionRule:
    """A `DecisionRule` for `name` with its defaults filled and `parameters` over them."""
    if name not in RULES:
        raise KeyError(f"no rule {name!r}; have {sorted(RULES)}")
    defaults = rule_defaults(name)
    unknown = set(parameters) - set(defaults)
    if unknown:
        raise ValueError(f"{name} has no parameters {sorted(unknown)}")
    return DecisionRule(name=name, version=RULES[name][0], parameters={**defaults, **parameters})


def apply(rule: DecisionRule, result: AnalysisResult) -> Decision:
    """Apply `rule` to `result`. Raises KeyError for an unknown rule and ValueError when the rule's
    version or parameters do not match the callable's (a verdict must be reproducible)."""
    if rule.name not in RULES:
        raise KeyError(f"no rule {rule.name!r}; have {sorted(RULES)}")
    version, fn = RULES[rule.name]
    if rule.version != version:
        raise ValueError(f"{rule.name} is version {version}, the rule says {rule.version}")
    defaults = rule_defaults(rule.name)
    if set(rule.parameters) != set(defaults):
        raise ValueError(
            f"{rule.name} takes {sorted(defaults)}; the rule carries {sorted(rule.parameters)}"
        )
    return fn(result, **rule.parameters)
