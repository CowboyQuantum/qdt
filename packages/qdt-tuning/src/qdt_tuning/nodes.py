"""Calibration nodes: the experiment, the method, the rule, as data (ADR 0048).

A node names logical channels, not instruments, so the same node runs on the simulator's stand and on
the bench's: both wire `P1` (a DC plunger), `P2_pulse` (its neighbour's pulse line on the sequencer) and
`sensor` (the charge sensor the sequencer reads). The sequencer's instrument id is the one stand-specific
value and is an argument.
"""

from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition, SymbolBinding
from qdt_schemas.modeling import CalibrationNode, FitModel
from qdt_schemas.pulse import Measure, PulseSequence, Step, Symbol

from .decisions import VIRTUAL_GATES_NAME, decision_rule

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
) -> SweepDefinition:
    """`P1` stepped by its DC line, `P2` pulsed inside the sequencer stage, the sensor read per pixel:
    the stability-diagram sweep the simulator's scenarios and the bench's stand both run."""
    return SweepDefinition(
        name=name,
        axes=(
            SweepAxis(name="P1", channel="P1", start=p1[0], stop=p1[1], num=n_outer),
            SweepAxis(name="P2", channel="P2_pulse", start=p2[0], stop=p2[1], num=n_inner),
        ),
        stage=SequencerStage(
            instrument=instrument,
            axes=("P2",),
            sequence=PulseSequence(
                name="read sensor at a P2 pulse level",
                body=(
                    Step(channel="P2_pulse", level=Symbol(name="v_p2", unit="V"), duration=step_ns),
                    Measure(channel="sensor", duration=measure_ns, result="I_sensor"),
                ),
            ),
            bindings=(SymbolBinding(symbol="v_p2", axis="P2"),),
        ),
    )


def charge_lattice(
    *,
    instrument: str,
    p1: tuple[float, float] = (0.03, 0.18),
    p2: tuple[float, float] = (0.03, 0.18),
    n: int = 96,
    max_cross_ratio: float = 0.6,
) -> CalibrationNode:
    """The first node: a stability diagram in a window where both dots are occupied, the charge
    lattice from its transitions (ADR 0029), the virtual-gate matrix as the decision."""
    return CalibrationNode(
        node_id="charge-lattice",
        description=(
            "Electrons per volt on each dot from each plunger, from the honeycomb's lattice; the "
            "virtual-gate matrix that removes the cross-talk."
        ),
        definition=stability_diagram(
            instrument=instrument, p1=p1, p2=p2, n_outer=n, n_inner=n, name="charge lattice"
        ),
        method=FitModel(
            name=TRANSITIONS_METHOD, version=TRANSITIONS_VERSION, parameters=TRANSITIONS_DEFAULTS
        ),
        decision=decision_rule(VIRTUAL_GATES_NAME, max_cross_ratio=max_cross_ratio),
    )
