"""Calibration nodes against the simulator (ADR 0048, 0049, 0088): one node runs and decides; a tune-up
chains nodes through their bound inputs; committed outcomes are reproduced and agree with the device's
truth (Phantom's); and the outcomes a node gives when its method or its stand fails. The nodes take the
simulated stand's windows (`SIMULATED_NODES`), as the server offers them."""

import pathlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis.sensor_peak import WING_WIDTHS
from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.modeling import CalibrationNode, SimResult, SimScenario
from qdt_server.app import SIMULATED_NODES
from qdt_server.tuning import run_node, run_tuneup
from qdt_sim.scenarios import (
    DEVICE_ID,
    DEVICES,
    default_stand,
    device_for,
    lattice_truth,
    sensor_truth,
)
from qdt_tuning import (
    charge_lattice,
    sensor_operating_point_node,
    sensor_wing_node,
    virtual_gate_matrix,
    virtual_lattice,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

A, B = "two-dot-sige-a", "two-dot-sige-b"
DEFAULT = SimScenario(
    scenario_id="default-occupied-window",
    description="the default device with its noise, noise seed 1; the charge-lattice node's window",
    device=A,
    device_sha256=DEVICES[A],
    seed=1,
)
QUIET = SimScenario(
    scenario_id="default-quiet",
    description="the default device, noise off",
    device=A,
    device_sha256=DEVICES[A],
    noise=False,
)
SECOND = SimScenario(
    scenario_id="second-device",
    description="a second disorder draw of the same layout, noise off: the full chain finds it (ADR 0088)",
    device=B,
    device_sha256=DEVICES[B],
    seed=2,
    noise=False,
)
WINDOWS = SIMULATED_NODES


def sensor_node() -> CalibrationNode:
    return sensor_operating_point_node(**WINDOWS["sensor-operating-point"])


def wing_node() -> CalibrationNode:
    return sensor_wing_node(**WINDOWS["sensor-wing"])


def lattice_node(**kwargs) -> CalibrationNode:
    return charge_lattice(instrument=DEVICE_ID, **WINDOWS["charge-lattice"] | kwargs)


def virtual_node() -> CalibrationNode:
    return virtual_lattice(instrument=DEVICE_ID, **WINDOWS["virtual-lattice"])


NodeBuilders = Sequence[Callable[[], CalibrationNode]]
FOUR_NODES: NodeBuilders = [
    sensor_node,
    wing_node,
    lambda: lattice_node(sensor_gate="SG"),
    lambda: virtual_lattice(instrument=DEVICE_ID, sensor_gate="SG", **WINDOWS["virtual-lattice"]),
]
"""The full chain (ADR 0062), both lattices read with the sensor `SENSOR_TAIL_V` from its wing (ADR 0090)."""
SCENARIOS: dict[str, tuple[SimScenario, NodeBuilders]] = {
    "sensor_operating_point_second": (SECOND, [sensor_node]),
    "sensor_wing_second": (SECOND, [sensor_node, wing_node]),
    "virtual_lattice_second": (SECOND, FOUR_NODES),
    "charge_lattice_default": (DEFAULT, [lattice_node]),
    "charge_lattice_quiet": (QUIET, [lattice_node]),
    "virtual_lattice_quiet": (QUIET, [lattice_node, virtual_node]),
}
"""Fixture name → (scenario, the tune-up's nodes in order); the fixture is the last node's outcome.
`scripts/make_tuning_fixtures.py` writes one file each. No noisy virtual lattice (ADR 0091): on Phantom
0.4.0 its gate noise (Phantom #50) leaves that node rejected for 5 of noise seeds 0–9, seed 1 among them,
so the noisy chain is pinned through the charge-lattice node."""


def truth_for(scenario: SimScenario, node_id: str) -> dict[str, float]:
    """The device's values for the node's decided quantities, by the node's output names."""
    lattice = lattice_truth(scenario)
    L = np.array([[lattice["l_11"], lattice["l_12"]], [lattice["l_21"], lattice["l_22"]]])
    M = virtual_gate_matrix(L)
    if node_id == "charge-lattice":
        return (
            lattice
            | {f"m_{i + 1}{j + 1}": float(M[i, j]) for i in range(2) for j in range(2)}
            | {"c_21": float(M[1, 0] / M[0, 0]), "c_12": float(M[0, 1] / M[1, 1])}
        )
    if node_id == "sensor-operating-point":
        t = sensor_truth(scenario)
        return {k: t[k] for k in ("sg_peak_v", "period", "charging_energy", "lever_arm")} | {
            "sg_operating_v": t["sg_peak_v"] + WINDOWS["sensor-operating-point"]["flank_offset_v"]
        }
    if node_id == "sensor-wing":
        bias = wing_node().definition.levels[0].value  # the node's linear-response bias
        t = sensor_truth(scenario, bias_v=bias)
        return {  # the width of the sech² with the broadened peak's wing (ADR 0090)
            "sg_peak_v": t["sg_peak_v"],
            "sg_width_v": (t["sg_wing_v"] - t["sg_peak_v"]) / WING_WIDTHS,
            "sg_operating_v": t["sg_wing_v"],
            "sensitivity_a_per_v": t["sensitivity_a_per_v"],
        }
    if node_id == "virtual-lattice":
        # in virtual coordinates the lattice is L · C, diagonal when M is right
        C = np.array([[1.0, M[0, 1] / M[1, 1]], [M[1, 0] / M[0, 0], 1.0]])
        LC = L @ C
        return {
            "residual_a": float(LC[0, 1] / LC[0, 0]),
            "residual_b": float(LC[1, 0] / LC[1, 1]),
            "l_11": float(LC[0, 0]),
            "l_22": float(LC[1, 1]),
        }
    raise KeyError(node_id)


def registry_for(root: pathlib.Path) -> Registry:
    registry = Registry(root / "registry")
    registry.register_device(
        DeviceRecord(
            device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
        )
    )
    return registry


def run_scenario(scenario: SimScenario, builders: NodeBuilders, root: pathlib.Path):
    """The tune-up's outcomes; the last node's outcome, result and truth are the fixture's."""
    registry = registry_for(root)
    nodes = [b() for b in builders]
    outcomes = run_tuneup(
        nodes,
        default_stand(),
        {DEVICE_ID: device_for(scenario)},
        registry,
        root / "outbox",
        device_id=DEVICE_ID,
        scenario_id=scenario.scenario_id,
    )
    last = outcomes[-1]
    result = registry.result(last.result_id) if last.result_id else None
    return outcomes, result, truth_for(scenario, nodes[-1].node_id)


TOLERANCES = {
    # name → (relative, absolute) against the device's truth, per decided quantity; the lattice's cross
    # terms absolutely (ADR 0088). The gate 1/f noise (Phantom #50) moves dot 1's lines between rows,
    # which a stability sweep takes 0.64 s apart, so it bends their spacing and tilt, l_11 and l_12;
    # dot 2's lines are crossed within a row and stay put (ADR 0091). The noisy default lands 5.3 % low
    # on l_11, 1.05 e/V low on l_12 and 0.048 off on m_12 and c_12, so those bounds are 6 %, 1.2 e/V
    # and 0.06, the rest 1.5 %, 0.3 e/V and 0.015 (ADR 0090). The quiet scenarios land within 0.6 %,
    # 0.16 e/V and 0.008: on Phantom 0.4.0 about 40 % of the window is one merged dot, which reads the
    # cross terms about 6 % high
    "l_11": (0.06, 0.0),
    "l_22": (0.015, 0.0),
    "l_12": (0.0, 1.2),
    "l_21": (0.0, 0.3),
    "m_11": (0.0, 0.015),
    "m_12": (0.0, 0.06),
    "m_21": (0.0, 0.015),
    "m_22": (0.0, 0.015),
    "c_21": (0.0, 0.015),
    "c_12": (0.0, 0.06),
    "residual_a": (0.0, 0.02),
    "residual_b": (0.0, 0.02),
    # the sensor's (ADR 0090): positions within 0.5 mV, a fifth of its broadened peak's ~2.3 mV width
    # (the diamonds' gate pixel is ~0.9 mV, the wing trace's 40 µV); the width is the sech² width with
    # the broadened peak's wing; period and lever arm looser, since the diamond window charges each dot
    # through the sensor gate, while Phantom's truth holds the dots' charge fixed
    "sg_peak_v": (0.0, 5e-4),
    "sg_operating_v": (0.0, 5e-4),
    "sg_width_v": (0.1, 0.0),
    "sensitivity_a_per_v": (0.15, 0.0),
    "period": (0.05, 0.0),
    "charging_energy": (0.05, 0.0),
    "lever_arm": (0.1, 0.0),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_tuneup_reproduces_its_committed_outcome_and_the_devices_truth(name, tmp_path):
    scenario, builders = SCENARIOS[name]
    fixture = SimResult.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    nodes = [b() for b in builders]
    assert fixture.scenario == scenario and fixture.node_id == nodes[-1].node_id
    outcomes, result, truth = run_scenario(scenario, builders, tmp_path)
    assert [o.node_id for o in outcomes] == [n.node_id for n in nodes]
    assert all(o.status == "accepted" for o in outcomes), [(o.node_id, o.message) for o in outcomes]
    last = outcomes[-1]
    assert last.scenario_id == scenario.scenario_id and result is not None
    # the same scenario decides the same numbers (the simulator is seeded; the method is deterministic)
    assert set(last.outputs) == set(fixture.outcome.outputs)
    for k, v in fixture.outcome.outputs.items():
        assert last.outputs[k] == pytest.approx(v, rel=1e-6), k
    assert {e.name: e.value for e in result.estimates} == pytest.approx(
        {e.name: e.value for e in fixture.estimates}, rel=1e-6
    )
    # and they agree with the device
    assert fixture.truth == pytest.approx(truth, rel=1e-9)
    for k, v in truth.items():
        rel, absolute = TOLERANCES[k]
        assert last.outputs[k] == pytest.approx(v, rel=rel, abs=absolute), (k, last.outputs[k], v)
    # the record and the result are in the registry, with the node's method as the result's provenance
    registry = Registry(tmp_path / "registry")
    assert registry.get(last.record_id).definition_name == nodes[-1].definition.name
    assert registry.result(last.result_id).method == nodes[-1].method


def test_the_virtual_lattice_straightens_what_the_charge_lattice_found(tmp_path):
    """The DAG edge in one picture: cross ratios of ≈ 0.1 in real gates, within 0.015 of zero in the
    virtual gates built from the first node's coefficients (residual_a is −0.0125 on Phantom 0.4.0, whose
    merged corner of the window reads the first node's cross terms about 6 % high, ADR 0091)."""
    outcomes, _, _ = run_scenario(QUIET, SCENARIOS["virtual_lattice_quiet"][1], tmp_path)
    first, second = outcomes
    assert first.outputs["l_12"] / first.outputs["l_11"] > 0.05
    assert abs(second.outputs["residual_a"]) < 0.015 and abs(second.outputs["residual_b"]) < 0.015
    bound = Registry(tmp_path / "registry").get(second.record_id)
    assert bound.definition_name == "virtual-gate lattice"


def test_a_tuneup_stops_at_the_first_node_that_is_not_accepted(tmp_path):
    """A charge-lattice node whose rule cannot accept (an impossible cross-ratio limit): the second
    node is not run, and its missing input is the reason the tune-up ends there."""
    registry = registry_for(tmp_path)
    strict = lattice_node(max_cross_ratio=0.01)
    outcomes = run_tuneup(
        [strict, virtual_node()],
        default_stand(),
        {DEVICE_ID: device_for(QUIET)},
        registry,
        tmp_path / "outbox",
        device_id=DEVICE_ID,
    )
    assert [o.status for o in outcomes] == ["rejected"]
    assert "cross-capacitance" in outcomes[0].message
    with pytest.raises(ValueError, match="not in the tune-up"):
        run_tuneup(
            [virtual_node()],
            default_stand(),
            {},
            registry,
            tmp_path / "outbox",
            device_id=DEVICE_ID,
        )


def test_a_window_without_a_lattice_is_a_failed_outcome_with_its_record_kept(tmp_path):
    """The empty-dot corner with the default noise: no transitions, so the method fails; the outcome says
    so, names the record and the (failed) result, and carries no outputs. (With noise off the map is
    nearly constant and the method reports a degenerate lattice as `ok`: a method weakness, STATUS.md.)"""
    registry = registry_for(tmp_path)
    empty = {"p1": (-0.65, -0.6), "p2": (-1.25, -1.2), "n": 24}  # both plungers about −0.6 V
    node = lattice_node(**empty)
    outcome, result = run_node(
        node,
        default_stand(),
        {DEVICE_ID: device_for(DEFAULT)},
        registry,
        tmp_path / "outbox",
        device_id=DEVICE_ID,
    )
    assert outcome.status == "failed" and outcome.outputs == {}, outcome.message
    assert (
        outcome.record_id and outcome.result_id and result is not None and result.status == "failed"
    )
    assert "the method failed" in outcome.message


def test_a_node_with_an_unknown_method_is_a_definition_error(tmp_path):
    node = lattice_node()
    node = node.model_copy(
        update={"method": node.method.model_copy(update={"name": "qdt_analysis.nope"})}
    )
    with pytest.raises(KeyError, match="no method"):
        run_node(
            node, default_stand(), {}, Registry(tmp_path / "r"), tmp_path / "o", device_id=DEVICE_ID
        )


def test_a_stand_that_cannot_run_the_node_is_a_failed_outcome(tmp_path):
    registry = registry_for(tmp_path)
    node = charge_lattice(instrument="nope")  # no such sequencer on the stand
    outcome, result = run_node(
        node,
        default_stand(),
        {DEVICE_ID: device_for(QUIET)},
        registry,
        tmp_path / "outbox",
        device_id=DEVICE_ID,
    )
    assert outcome.status == "failed" and outcome.record_id is None and result is None
    assert "nope" in outcome.message


# --- the tune-up through the API (ADR 0050) ------------------------------------------------------------


def wait_tuneup(client, tuneup_id: str, timeout: float = 60.0):
    import time

    from qdt_schemas.control import TuneUp

    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        tuneup = TuneUp.model_validate(client.get(f"/tuneups/{tuneup_id}").json())
        if tuneup.state not in ("queued", "running"):
            return tuneup
        time.sleep(0.1)
    raise TimeoutError(tuneup_id)


def test_a_tuneup_runs_through_the_api_and_its_outcomes_are_in_the_registry(client):
    """GET /nodes offers the templates for the stand's sequencer; POST /tuneups runs them in order on a
    scenario, each node's sweep a Run on the stream; the TuneUp completes with both accepted; the
    outcomes are stored and point at their records and results."""
    nodes = client.get("/nodes").json()
    assert [n["node_id"] for n in nodes] == [
        "sensor-operating-point",
        "sensor-wing",
        "charge-lattice",
        "virtual-lattice",
    ]
    assert nodes[1]["depends_on"] == ["sensor-operating-point"] and nodes[1]["holds"] == {"SG": "sg_operating_v"}
    assert nodes[2]["depends_on"] == ["sensor-wing"]
    assert nodes[2]["definition"]["levels"][0]["channel"] == "SG"
    r = client.post(
        "/tuneups",
        json={
            "node_ids": [
                "virtual-lattice",
                "charge-lattice",
                "sensor-wing",
                "sensor-operating-point",
            ],  # any order
            "scenario": SECOND.model_dump(mode="json"),
            "options": {"campaign": "tuneup"},
        },
    )
    assert r.status_code == 202, r.text
    tuneup = wait_tuneup(client, r.json()["tuneup_id"])
    assert tuneup.state == "completed", tuneup.message
    assert [n.node_id for n in tuneup.nodes] == [
        "sensor-operating-point",
        "sensor-wing",
        "charge-lattice",
        "virtual-lattice",
    ]
    assert tuneup.scenario_id == SECOND.scenario_id and tuneup.attrs["device"] == B
    assert tuneup.name == "sensor-operating-point → sensor-wing → charge-lattice → virtual-lattice"
    assert [o.status for o in tuneup.outcomes] == ["accepted"] * 4
    first, wing, _, second = tuneup.outcomes
    sensor = sensor_truth(SECOND)
    assert first.outputs["sg_peak_v"] == pytest.approx(
        sensor["sg_peak_v"], abs=TOLERANCES["sg_peak_v"][1]
    )
    same_wing = (sensor["sg_wing_v"] - sensor["sg_peak_v"]) / WING_WIDTHS  # ADR 0090
    assert wing.outputs["sg_width_v"] == pytest.approx(same_wing, rel=0.1)
    assert abs(second.outputs["residual_a"]) < 0.02 and second.tuneup_id == tuneup.tuneup_id
    # every node's sweep was a run on the server, with the tune-up's options
    runs = client.get("/runs").json()
    assert [x["definition_name"] for x in runs] == [
        "sensor diamonds",
        "sensor peak",
        "charge lattice",
        "virtual-gate lattice",
    ]
    assert all(x["state"] == "completed" and x["attrs"]["campaign"] == "tuneup" for x in runs)
    # the outcomes are durable and point at durable records and results
    stored = client.get("/outcomes", params={"tuneup_id": tuneup.tuneup_id}).json()
    assert [o["outcome_id"] for o in stored] == [o.outcome_id for o in tuneup.outcomes]
    for o in stored:
        assert client.get(f"/records/{o['record_id']}").status_code == 200
        assert client.get(f"/results/{o['result_id']}").json()["status"] == "ok"
    assert client.get(f"/outcomes/{second.outcome_id}").json()["node_id"] == "virtual-lattice"
    assert client.get("/outcomes/" + "0" * 32).status_code == 404
    assert [t["tuneup_id"] for t in client.get("/tuneups").json()] == [tuneup.tuneup_id]
    assert client.get("/tuneups/" + "0" * 32).status_code == 404
    assert client.post(f"/tuneups/{tuneup.tuneup_id}/stop").status_code == 409
    # ADR 0062: the wing node holds the sensor gate where it decided; a retune alone re-centres on it
    held = {lv["channel"]: lv["value"] for lv in client.get("/levels").json()}
    assert held["SG"] == pytest.approx(wing.outputs["sg_operating_v"])
    state = client.get("/stand/state").json()  # ADR 0085: a version under the tune-up's name
    assert state["set_by"] == f"tune-up {tuneup.tuneup_id}"
    assert "'sensor-wing' accepted" in state["reason"]
    r = client.post(
        "/tuneups", json={"node_ids": ["sensor-wing"], "scenario": SECOND.model_dump(mode="json")}
    )
    assert r.status_code == 202, r.text
    retune = wait_tuneup(client, r.json()["tuneup_id"])
    assert retune.state == "completed", retune.message
    assert retune.outcomes[0].outputs["sg_operating_v"] == pytest.approx(
        wing.outputs["sg_operating_v"], abs=TOLERANCES["sg_operating_v"][1]
    )
    window = retune.nodes[0].definition.axes[0]
    span = WINDOWS["sensor-wing"]["span_v"]
    assert (window.start, window.stop) == pytest.approx((held["SG"] - span, held["SG"] + span))


def test_a_tuneup_on_a_scenario_whose_device_file_hashes_otherwise_fails(client):
    """ADR 0088: the scenario pins its device file by hash, and the server's backends check it."""
    wrong = SECOND.model_copy(update={"device_sha256": DEVICES[A]})
    r = client.post(
        "/tuneups",
        json={"node_ids": ["sensor-operating-point"], "scenario": wrong.model_dump(mode="json")},
    )
    assert r.status_code == 202, r.text
    tuneup = wait_tuneup(client, r.json()["tuneup_id"])
    assert tuneup.state == "failed" or tuneup.outcomes[0].status == "failed"
    assert "hashes to" in (tuneup.message + " ".join(o.message for o in tuneup.outcomes))


def test_a_tuneup_refuses_unknown_nodes_and_stops_when_asked(client):
    assert client.post("/tuneups", json={"node_ids": ["nope"]}).status_code == 400
    assert client.post("/tuneups", json={"node_ids": []}).status_code == 422
    # a dependent without its dependency is a 400, not a run
    missing = client.post(
        "/tuneups",
        json={"node_ids": ["charge-lattice"], "scenario": SECOND.model_dump(mode="json")},
    )
    assert missing.status_code == 400 and "sensor-wing" in missing.json()["detail"]
    r = client.post(
        "/tuneups",
        json={
            "node_ids": [
                "sensor-operating-point",
                "sensor-wing",
                "charge-lattice",
                "virtual-lattice",
            ],
            "scenario": SECOND.model_dump(mode="json"),
        },
    )
    tuneup_id = r.json()["tuneup_id"]
    stopped = client.post(f"/tuneups/{tuneup_id}/stop")
    assert stopped.status_code == 200 and stopped.json()["state"] in (
        "stopped",
        "running",
        "queued",
    )
    final = wait_tuneup(client, tuneup_id)
    assert (
        final.state == "stopped"
        and "stopped by request" in final.message
        or final.state == "stopped"
    )
    assert len(final.outcomes) <= 1
