"""The tune-up's order (ADR 0050): dependencies first, stable otherwise, cycles and strangers refused."""

import pytest

from qdt_schemas.activity import SensedLevel, SweepAxis, SweepDefinition
from qdt_schemas.modeling import CalibrationNode, DecisionRule, FitModel
from qdt_tuning import TEMPLATES, charge_lattice, order, virtual_lattice


def node(i: str, *deps: str) -> CalibrationNode:
    return CalibrationNode(
        node_id=i,
        definition=SweepDefinition(
            name="d",
            axes=(SweepAxis(name="g", channel="g", start=0, stop=1, num=2),),
            sensed=(SensedLevel(name="I", channel="s"),),
        ),
        method=FitModel(name="m", version="1"),
        decision=DecisionRule(name="r", version="1"),
        depends_on=deps,
    )


def test_order_puts_dependencies_first_and_keeps_the_given_order_otherwise():
    a, b, c, d = node("a"), node("b", "a"), node("c", "a"), node("d", "b", "c")
    assert [n.node_id for n in order([d, c, b, a])] == ["a", "c", "b", "d"]
    assert [n.node_id for n in order([a, b, c, d])] == ["a", "b", "c", "d"]
    assert [n.node_id for n in order([c, a])] == ["a", "c"]
    assert [
        n.node_id for n in order([virtual_lattice(instrument="x"), charge_lattice(instrument="x")])
    ] == [
        "charge-lattice",
        "virtual-lattice",
    ]


def test_order_refuses_cycles_strangers_and_repeats():
    with pytest.raises(ValueError, match="cycle"):
        order([node("a", "b"), node("b", "a")])
    with pytest.raises(ValueError, match="not in the tune-up"):
        order([node("b", "a")])
    with pytest.raises(ValueError, match="unique"):
        order([node("a"), node("a")])


def test_templates_build_every_node_for_a_stands_sequencer_and_sensor_gate():
    built = {k: make("opx", "SG") for k, make in TEMPLATES.items()}
    assert set(built) == {"sensor-operating-point", "sensor-wing", "charge-lattice", "virtual-lattice"}
    assert built["charge-lattice"].definition.stage.instrument == "opx"
    assert built["charge-lattice"].depends_on == ("sensor-wing",)
    assert built["sensor-wing"].depends_on == ("sensor-operating-point",)
    assert [n.node_id for n in order(reversed(list(built.values())))] == [
        "sensor-operating-point",
        "sensor-wing",
        "charge-lattice",
        "virtual-lattice",
    ]
    # a retune (ADR 0062): the wing node alone is allowed, its inputs fall back to the held level
    assert [n.node_id for n in order([built["sensor-wing"]])] == ["sensor-wing"]
    with pytest.raises(ValueError, match="not in the tune-up"):
        order([built["charge-lattice"]])  # no fallback on its binding
    # without a sensor gate the charge lattice stands alone (the sensor node is not offered then)
    alone = TEMPLATES["charge-lattice"]("opx", None)
    assert alone.depends_on == () and alone.inputs == ()
