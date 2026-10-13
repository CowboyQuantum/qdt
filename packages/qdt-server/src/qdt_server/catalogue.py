"""The curated methods the API offers (ADR 0031, 0034): one `MethodSpec` per method, plus the callable.

A spec's parameters must match the function's keyword arguments and defaults; `tests/test_catalogue.py`
pins that, so a method that changes its signature changes its spec in the same commit.
"""

from collections.abc import Callable

from qdt_analysis import diamonds, transitions
from qdt_analysis.transitions import Analysis
from qdt_schemas.control import EstimateSpec, MethodSpec, ParameterSpec
from qdt_schemas.data import AttrValue
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.payload_hdf5 import Payload

Method = Callable[..., Analysis]

_DETECTION = (
    ParameterSpec(
        name="variable",
        kind="str",
        default="",
        description="Data variable; default: the first 2-D one.",
    ),
    ParameterSpec(
        name="smooth_px",
        kind="float",
        default=1.0,
        unit="px",
        minimum=0.0,
        description="Gaussian smoothing before the gradient.",
    ),
    ParameterSpec(
        name="threshold_rel",
        kind="float",
        default=0.3,
        minimum=0.0,
        maximum=1.0,
        description="Ridge threshold as a fraction of the 99.5th percentile of the gradient.",
    ),
    ParameterSpec(
        name="threshold_noise",
        kind="float",
        default=5.0,
        minimum=0.0,
        description="Ridge threshold floor in gradient-noise standard deviations.",
    ),
    ParameterSpec(
        name="min_separation_deg",
        kind="float",
        default=15.0,
        unit="deg",
        minimum=0.0,
        maximum=90.0,
        description="Minimum angle between the two edge families.",
    ),
    ParameterSpec(
        name="window_deg",
        kind="float",
        default=12.0,
        unit="deg",
        minimum=0.0,
        maximum=90.0,
        description="Angular window around a family's direction.",
    ),
    ParameterSpec(
        name="min_segment_px",
        kind="int",
        default=6,
        unit="px",
        minimum=2,
        description="Shorter runs are dropped.",
    ),
    ParameterSpec(
        name="max_segments", kind="int", default=200, minimum=1, description="Cap on overlays."
    ),
)

METHODS: dict[str, tuple[MethodSpec, Method]] = {
    transitions.NAME: (
        MethodSpec(
            name=transitions.NAME,
            version=transitions.VERSION,
            title="Charge transitions",
            description="Transition segments on a stability diagram, and the honeycomb's charge lattice (electrons per volt on each dot from each gate).",
            applies_to="map_2d",
            parameters=(
                *_DETECTION,
                ParameterSpec(
                    name="min_periods",
                    kind="float",
                    default=5.0,
                    minimum=1.0,
                    description="Lattice peaks closer to the origin than this many periods per map are ignored.",
                ),
                ParameterSpec(
                    name="zero_pad",
                    kind="int",
                    default=4,
                    minimum=1,
                    description="Zero-padding factor of the spectrum.",
                ),
            ),
            estimates=(
                EstimateSpec(
                    name="a_per_volt_row",
                    unit="1/V",
                    description="Electrons on dot a per volt of the row gate.",
                ),
                EstimateSpec(
                    name="a_per_volt_col",
                    unit="1/V",
                    description="Electrons on dot a per volt of the column gate.",
                ),
                EstimateSpec(
                    name="b_per_volt_row",
                    unit="1/V",
                    description="Electrons on dot b per volt of the row gate.",
                ),
                EstimateSpec(
                    name="b_per_volt_col",
                    unit="1/V",
                    description="Electrons on dot b per volt of the column gate.",
                ),
                EstimateSpec(name="cross_ratio_a", description="Cross-capacitance ratio of dot a."),
                EstimateSpec(name="cross_ratio_b", description="Cross-capacitance ratio of dot b."),
            ),
        ),
        transitions.detect_transitions,
    ),
    diamonds.NAME: (
        MethodSpec(
            name=diamonds.NAME,
            version=diamonds.VERSION,
            title="Coulomb diamonds",
            description="Diamond edges on a (gate, bias) map; degeneracy points, period, charging energy, lever arm and edge slopes.",
            applies_to="map_2d",
            parameters=(
                *_DETECTION,
                ParameterSpec(
                    name="point_tolerance_px",
                    kind="float",
                    default=3.0,
                    unit="px",
                    minimum=0.0,
                    description="Zero-bias crossings closer than this are one degeneracy point.",
                ),
            ),
            estimates=(
                EstimateSpec(
                    name="period", unit="V", description="Spacing of the degeneracy points."
                ),
                EstimateSpec(
                    name="charging_energy", unit="eV", description="e times the apex bias."
                ),
                EstimateSpec(
                    name="lever_arm", unit="eV/V", description="Charging energy per period."
                ),
                EstimateSpec(name="slope_rising", unit="V/V", description="Rising edge slope."),
                EstimateSpec(name="slope_falling", unit="V/V", description="Falling edge slope."),
            ),
        ),
        diamonds.detect_diamonds,
    ),
}


def specs() -> list[MethodSpec]:
    return [spec for spec, _ in METHODS.values()]


def run_method(
    name: str, record: MeasurementRecord, payload: Payload, parameters: dict[str, AttrValue]
) -> Analysis:
    """Run the curated method `name` with `parameters` checked against its spec."""
    if name not in METHODS:
        raise KeyError(f"no method {name!r}; have {sorted(METHODS)}")
    spec, method = METHODS[name]
    return method(record, payload, **spec.resolve(parameters))
