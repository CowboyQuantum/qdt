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


def test_templates_build_every_node_for_a_stands_sequencer():
    built = {k: make("opx") for k, make in TEMPLATES.items()}
    assert set(built) == {"charge-lattice", "virtual-lattice"}
    assert all(n.definition.stage.instrument == "opx" for n in built.values())
    assert [n.node_id for n in order(built.values())] == ["charge-lattice", "virtual-lattice"]
