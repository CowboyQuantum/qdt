"""Calibration nodes: the experiment, the method, the rule, as data (ADR 0048).

A node names logical channels, not instruments, so the same node runs on the simulator's stand and on
the bench's: both wire `P1` (a DC plunger), `P2_pulse` (its neighbour's pulse line on the sequencer) and
`sensor` (the charge sensor the sequencer reads). The sequencer's instrument id is the one stand-specific
value and is an argument.
"""

from collections.abc import Callable

from qdt_schemas.activity import (
    FixedLevel,
    SensedLevel,
    SequencerStage,
    SweepAxis,
    SweepDefinition,
    SymbolBinding,
)
from qdt_schemas.modeling import CalibrationNode, FitModel, InputBinding
from qdt_schemas.pulse import Affine, Measure, PulseSequence, Step, Symbol

from .decisions import (
    SENSOR_OPERATING_POINT_NAME,
    SENSOR_WING_NAME,
    STRAIGHTENED_NAME,
    VIRTUAL_GATES_NAME,
    decision_rule,
)

TRANSITIONS_METHOD = "qdt_analysis.transitions.detect_transitions"
TRANSITIONS_VERSION = "1"
TRANSITIONS_DEFAULTS = {
    "variable": "",
    "smooth_px": 1.0,
    "threshold_rel": 0.3,
    "threshold_noise": 5.0,
    "min_separation_deg": 15.0,
    "window_deg": 12.0,
    "min_segment_px": 6,
    "max_segments": 200,
    "min_periods": 5.0,
    "zero_pad": 4,
}
"""The method's defaults, as its `FitModel` carries them; the server's catalogue test pins the method's
signature and `test_nodes.py` pins these against it."""


def stability_diagram(
    *,
    instrument: str,
    p1: tuple[float, float],
    p2: tuple[float, float],
    n_outer: int = 96,
    n_inner: int = 96,
    step_ns: int = 500,
    measure_ns: int = 2000,
    name: str = "stability diagram",
    virtual: bool = False,
) -> SweepDefinition:
    """`P1` stepped by its DC line, `P2` pulsed inside the sequencer stage, the sensor read per pixel:
    the stability-diagram sweep the simulator's scenarios and the bench's stand both run.

    `virtual=True` makes both axes virtual gates (ADR 0049) with their coefficients left at 0 for
    `InputBinding`s to fill: the outer axis couples `P2` (the DC line) by `c_21` volts per volt of `P1`,
    and the inner pulse steps `P1_pulse` by `c_12` × the `P2` pulse level alongside `P2_pulse`.
    """
    v_p2 = Symbol(name="v_p2", unit="V")
    body: tuple = (Step(channel="P2_pulse", level=v_p2, duration=step_ns),)
    if virtual:
        body = (
            Step(channel="P1_pulse", level=Affine(symbol=v_p2, scale=0.0), duration=step_ns),
            Step(channel="P2_pulse", level=v_p2, duration=step_ns),
        )
    return SweepDefinition(
        name=name,
        axes=(
            SweepAxis(
                name="P1",
                channel="P1",
                start=p1[0],
                stop=p1[1],
                num=n_outer,
                couplings={"P2": 0.0} if virtual else {},
            ),
            SweepAxis(name="P2", channel="P2_pulse", start=p2[0], stop=p2[1], num=n_inner),
        ),
        stage=SequencerStage(
            instrument=instrument,
            axes=("P2",),
            sequence=PulseSequence(
                name="read sensor at a P2 pulse level" + (" in virtual gates" if virtual else ""),
                body=(*body, Measure(channel="sensor", duration=measure_ns, result="I_sensor")),
            ),
            bindings=(SymbolBinding(symbol="v_p2", axis="P2"),),
        ),
    )


DIAMONDS_METHOD = "qdt_analysis.diamonds.detect_diamonds"
DIAMONDS_VERSION = "1"
DIAMONDS_DEFAULTS = {
    "variable": "",
    "smooth_px": 1.0,
    "threshold_rel": 0.3,
    "threshold_noise": 5.0,
    "min_separation_deg": 15.0,
    "window_deg": 12.0,
    "min_segment_px": 6,
    "max_segments": 200,
    "point_tolerance_px": 3.0,
}
"""The diamonds method's defaults, as its `FitModel` carries them (pinned against the catalogue)."""


def coulomb_diamonds(
    *,
    sensor_gate: str = "SG",
    bias: str = "bias",
    sensor: str = "sensor",
    sg: tuple[float, float] = (-0.2, 0.2),
    bias_v: tuple[float, float] = (-1.5e-3, 1.5e-3),
    n: int = 64,
    name: str = "sensor diamonds",
) -> SweepDefinition:
    """The sensor's Coulomb diamonds (ADR 0030): the sensor gate stepped by its DC line against the
    source–drain bias on its DC line, the sensor current sensed at every point."""
    return SweepDefinition(
        name=name,
        axes=(
            SweepAxis(name="SG", channel=sensor_gate, start=sg[0], stop=sg[1], num=n),
            SweepAxis(name="V_sd", channel=bias, start=bias_v[0], stop=bias_v[1], num=n),
        ),
        sensed=(SensedLevel(name="I_sensor", channel=sensor),),
    )


def sensor_operating_point(
    *,
    sensor_gate: str = "SG",
    bias: str = "bias",
    sensor: str = "sensor",
    n: int = 64,
    flank_offset_v: float = 0.02,
    near_v: float = 0.0,
) -> CalibrationNode:
    """The sensor node: the Coulomb diamonds read by `detect_diamonds`, the sensor gate parked on the
    flank of the peak nearest `near_v` (ADR 0052). Its `sg_operating_v` is what the stability nodes hold."""
    return CalibrationNode(
        node_id="sensor-operating-point",
        description=(
            "The charge sensor's Coulomb diamonds: period, charging energy, lever arm; the sensor gate "
            "parked on a peak's flank, where the current changes fastest with charge."
        ),
        definition=coulomb_diamonds(sensor_gate=sensor_gate, bias=bias, sensor=sensor, n=n),
        method=FitModel(
            name=DIAMONDS_METHOD, version=DIAMONDS_VERSION, parameters=DIAMONDS_DEFAULTS
        ),
        decision=decision_rule(
            SENSOR_OPERATING_POINT_NAME, flank_offset_v=flank_offset_v, near_v=near_v
        ),
    )


SENSOR_PEAK_METHOD = "qdt_analysis.sensor_peak.fit_sensor_peak"
SENSOR_PEAK_VERSION = "1"
SENSOR_PEAK_DEFAULTS = {
    "variable": "",
    "near_v": 0.0,
    "near_centre": True,
    "side": "above",
    "min_r2": 0.5,
}
"""The sensor-peak method's defaults, as its `FitModel` carries them (pinned against the catalogue)."""


def sensor_gate_trace(
    *,
    sensor_gate: str = "SG",
    bias: str = "bias",
    sensor: str = "sensor",
    centre_v: float = 0.0,
    span_v: float = 0.05,
    n: int = 101,
    bias_v: float = 10e-6,
    name: str = "sensor peak",
) -> SweepDefinition:
    """The sensor gate stepped by its DC line through one Coulomb peak, `centre_v ± span_v`, the source–
    drain bias held at `bias_v`, the sensor current sensed at every point (ADR 0062). The bias must be
    well inside linear response (eV ≪ kT) for the fitted width to be the thermal one: a finite bias
    window broadens the peak by about eV/α in gate volts. 10 µV is a width-tenth for a 10 mV sensor at
    the simulator's lever arm; a warmer sensor tolerates more."""
    return SweepDefinition(
        name=name,
        axes=(
            SweepAxis(
                name="SG", channel=sensor_gate, start=centre_v - span_v, stop=centre_v + span_v, num=n
            ),
        ),
        sensed=(SensedLevel(name="I_sensor", channel=sensor),),
        levels=(FixedLevel(channel=bias, value=bias_v),),
    )


def sensor_wing(
    *,
    sensor_gate: str = "SG",
    bias: str = "bias",
    sensor: str = "sensor",
    span_v: float = 0.05,
    n: int = 101,
    bias_v: float = 10e-6,
    side: str = "above",
    min_sensitivity_a_per_v: float = 0.0,
) -> CalibrationNode:
    """The wing node (ADR 0062): a short sweep of the sensor gate through the peak the diamonds found,
    the peak fitted for its width, the gate parked on the fitted wing. After `sensor-operating-point`
    in a tune-up the window is centred on that node's peak; run on its own it is a *retune*, centred
    on the level the server holds for the sensor gate. Either way, once accepted the server holds the
    sensor gate at the wing (`holds`), and `charge-lattice` binds it from here."""
    window = sensor_gate_trace(
        sensor_gate=sensor_gate, bias=bias, sensor=sensor, span_v=span_v, n=n, bias_v=bias_v
    )
    return CalibrationNode(
        node_id="sensor-wing",
        description=(
            "The sensor's Coulomb peak fitted on a short gate sweep: its width, and the wing where the "
            "current changes fastest; the sensor gate parked there. Alone, a retune about the held level."
        ),
        definition=window,
        method=FitModel(
            name=SENSOR_PEAK_METHOD,
            version=SENSOR_PEAK_VERSION,
            parameters={**SENSOR_PEAK_DEFAULTS, "side": side},
        ),
        decision=decision_rule(SENSOR_WING_NAME, min_sensitivity_a_per_v=min_sensitivity_a_per_v),
        depends_on=("sensor-operating-point",),
        inputs=(
            InputBinding(
                node_id="sensor-operating-point",
                output="sg_peak_v",
                target="axes.0.start",
                offset=-span_v,
                held=sensor_gate,
            ),
            InputBinding(
                node_id="sensor-operating-point",
                output="sg_peak_v",
                target="axes.0.stop",
                offset=span_v,
                held=sensor_gate,
            ),
        ),
        holds={sensor_gate: "sg_operating_v"},
    )


def charge_lattice(
    *,
    instrument: str,
    p1: tuple[float, float] = (0.03, 0.18),
    p2: tuple[float, float] = (0.03, 0.18),
    n: int = 96,
    max_cross_ratio: float = 0.6,
    sensor_gate: str | None = None,
) -> CalibrationNode:
    """The first node: a stability diagram in a window where both dots are occupied, the charge
    lattice from its transitions (ADR 0029), the virtual-gate matrix as the decision. With
    `sensor_gate`, the node holds that gate at the wing `sensor-wing` fitted (ADR 0052, 0062): a held
    level in the sweep, bound from the upstream outcome."""
    definition = stability_diagram(
        instrument=instrument, p1=p1, p2=p2, n_outer=n, n_inner=n, name="charge lattice"
    )
    depends_on: tuple[str, ...] = ()
    inputs: tuple[InputBinding, ...] = ()
    if sensor_gate is not None:
        definition = definition.model_copy(
            update={"levels": (FixedLevel(channel=sensor_gate, value=0.0),)}
        )
        depends_on = ("sensor-wing",)
        inputs = (
            InputBinding(node_id="sensor-wing", output="sg_operating_v", target="levels.0.value"),
        )
    return CalibrationNode(
        node_id="charge-lattice",
        description=(
            "Electrons per volt on each dot from each plunger, from the honeycomb's lattice; the "
            "virtual-gate matrix that removes the cross-talk."
        ),
        definition=definition,
        method=FitModel(
            name=TRANSITIONS_METHOD, version=TRANSITIONS_VERSION, parameters=TRANSITIONS_DEFAULTS
        ),
        decision=decision_rule(VIRTUAL_GATES_NAME, max_cross_ratio=max_cross_ratio),
        depends_on=depends_on,
        inputs=inputs,
    )


def virtual_lattice(
    *,
    instrument: str,
    p1: tuple[float, float] = (0.03, 0.18),
    p2: tuple[float, float] = (0.03, 0.18),
    n: int = 96,
    max_residual_ratio: float = 0.05,
) -> CalibrationNode:
    """The second node: the same window swept in virtual gates built from `charge-lattice`'s
    compensation coefficients; the transitions must come out axis-aligned (ADR 0049)."""
    return CalibrationNode(
        node_id="virtual-lattice",
        description=(
            "The stability diagram in virtual gates: P2's DC line follows P1 by c_21, P1's pulse line "
            "follows the P2 pulse by c_12; the honeycomb's residual cross ratios must be near zero."
        ),
        definition=stability_diagram(
            instrument=instrument,
            p1=p1,
            p2=p2,
            n_outer=n,
            n_inner=n,
            name="virtual-gate lattice",
            virtual=True,
        ),
        method=FitModel(
            name=TRANSITIONS_METHOD, version=TRANSITIONS_VERSION, parameters=TRANSITIONS_DEFAULTS
        ),
        decision=decision_rule(STRAIGHTENED_NAME, max_residual_ratio=max_residual_ratio),
        depends_on=("charge-lattice",),
        inputs=(
            InputBinding(node_id="charge-lattice", output="c_21", target="axes.0.couplings.P2"),
            InputBinding(
                node_id="charge-lattice", output="c_12", target="stage.sequence.body.0.level.scale"
            ),
        ),
    )


TEMPLATES: dict[str, Callable[[str, str | None], CalibrationNode]] = {
    "sensor-operating-point": lambda instrument, sensor_gate: sensor_operating_point(
        sensor_gate=sensor_gate or "SG"
    ),
    "sensor-wing": lambda instrument, sensor_gate: sensor_wing(sensor_gate=sensor_gate or "SG"),
    "charge-lattice": lambda instrument, sensor_gate: charge_lattice(
        instrument=instrument, sensor_gate=sensor_gate
    ),
    "virtual-lattice": lambda instrument, sensor_gate: virtual_lattice(instrument=instrument),
}
"""Node id → constructor taking the stand's sequencer instrument id and its sensor-gate channel (None
when the stand has no `SG`): what a server offers (ADR 0050, 0052, 0062). With a sensor gate,
`charge-lattice` depends on `sensor-wing`, which depends on `sensor-operating-point` (or stands alone as
a retune); the two sensor nodes need `SG`, `bias` and `sensor` channels."""
