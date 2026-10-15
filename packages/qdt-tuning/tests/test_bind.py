"""Node inputs (ADR 0049): a path into the definition, a value from an upstream accepted outcome."""

from datetime import UTC, datetime

import pytest

from qdt_schemas.modeling import InputBinding, NodeOutcome
from qdt_tuning import bind, charge_lattice, set_path, virtual_lattice


def outcome(node_id="charge-lattice", status="accepted", **outputs) -> NodeOutcome:
    return NodeOutcome(
        outcome_id="ab" * 16,
        node_id=node_id,
        record_id="cd" * 16 if status != "failed" else None,
        result_id="ef" * 16 if status != "failed" else None,
        status=status,
        outputs=outputs if status == "accepted" else {},
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )


def test_set_path_walks_dicts_and_lists_and_names_what_it_cannot_reach():
    data = {"axes": [{"couplings": {"P2": 0.0}}], "stage": {"body": [{"level": {"scale": 0.0}}]}}
    set_path(data, "axes.0.couplings.P2", -0.2)
    set_path(data, "axes.0.couplings.SG", 0.1)  # a new key is allowed
    set_path(data, "stage.body.0.level.scale", -0.21)
    assert data["axes"][0]["couplings"] == {"P2": -0.2, "SG": 0.1}
    assert data["stage"]["body"][0]["level"]["scale"] == -0.21
    for bad in ("axes.x.couplings", "axes.3.couplings", "nope.a", "axes.0.couplings.P2.deeper"):
        with pytest.raises(KeyError):
            set_path(data, bad, 1.0)


def test_bind_fills_the_virtual_lattice_from_charge_lattices_coefficients():
    node = virtual_lattice(instrument="dot")
    assert node.depends_on == ("charge-lattice",)
    assert node.definition.axes[0].couplings == {"P2": 0.0}
    bound = bind(node, {"charge-lattice": outcome(c_21=-0.22, c_12=-0.21, m_11=1.0)})
    assert bound.definition.axes[0].couplings == {"P2": -0.22}
    assert bound.definition.stage.sequence.body[0].level.scale == -0.21
    assert bound.node_id == node.node_id and bound.inputs == node.inputs
    assert bind(charge_lattice(instrument="dot"), {}) == charge_lattice(instrument="dot")


def test_bind_refuses_missing_rejected_or_unknown_inputs():
    node = virtual_lattice(instrument="dot")
    with pytest.raises(KeyError, match="needs an outcome"):
        bind(node, {})
    with pytest.raises(ValueError, match="accepted"):
        bind(node, {"charge-lattice": outcome(status="rejected")})
    with pytest.raises(KeyError, match="no output"):
        bind(node, {"charge-lattice": outcome(c_21=-0.2)})
    broken = node.model_copy(
        update={
            "inputs": (InputBinding(node_id="charge-lattice", output="c_21", target="axes.0.num"),)
        }
    )
    with pytest.raises(ValueError, match="does not validate"):
        bind(broken, {"charge-lattice": outcome(c_21=-0.2)})  # num must be an integer ≥ 1


def test_bind_fills_a_held_level_from_the_sensor_node(tmp_path=None):
    """ADR 0052: the operating point flows into `levels.0.value`."""
    node = charge_lattice(instrument="dot", sensor_gate="SG")
    bound = bind(
        node, {"sensor-operating-point": outcome("sensor-operating-point", sg_operating_v=-0.04)}
    )
    assert bound.definition.levels[0].channel == "SG" and bound.definition.levels[0].value == -0.04
