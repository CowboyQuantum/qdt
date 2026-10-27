"""The stand state on the stand server (ADR 0075, 0085; Step 6c L0 row "StandState"): versions
round-trip through the registry and the latest is in force; a level and a compiled sweep beyond a
limit are refused against the simulated stand; the held point is not re-applied after a restart
without confirmation; every change says who made it and why."""

import time

from fastapi.testclient import TestClient

from qdt_registry import DSN_ENV, STORE_ENV, Registry
from qdt_schemas.control import Run
from qdt_schemas.operations import StandState
from qdt_server import Settings, create_app
from qdt_server.auth import new_token
from qdt_sim.scenarios import stability

LOOPBACK = ("127.0.0.1", 50000)
ELSEWHERE = ("192.0.2.10", 50000)
"""Another computer: a documentation address (RFC 5737 TEST-NET-1), no real desk (rule 7)."""


def definition(p1=(0.03, 0.18), n=8) -> dict:
    return stability(n, n, p1=p1, p2=(0.03, 0.18), name="limits test").model_dump(mode="json")


def server(root) -> TestClient:
    return TestClient(create_app(Settings(root=root, stream_port=0)), client=LOOPBACK)


def wait_for(client, run_id: str, timeout: float = 30.0) -> Run:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        run = Run.model_validate(client.get(f"/runs/{run_id}").json())
        if run.state not in ("queued", "running"):
            return run
        time.sleep(0.05)
    raise TimeoutError(run_id)


def limit(channel: str, low: float, high: float) -> dict:
    return {"channel": channel, "min_v": low, "max_v": high}


def setpoint(client, channel: str) -> float | None:
    return {r["channel"]: r for r in client.get("/levels/state").json()}[channel]["setpoint"]


def test_a_first_start_writes_version_1_and_every_change_is_the_next_version(tmp_path):
    with server(tmp_path / "registry") as c:
        first = StandState.model_validate(c.get("/stand/state").json())
        assert (first.version, first.set_by, first.limits, first.held) == (1, "qdt-server", (), ())
        r = c.post(
            "/stand/state",
            json={"limits": [limit("P1", -0.1, 0.2)], "reason": "P1 stays below 0.2 V"},
        )
        assert r.status_code == 201, r.text
        v2 = StandState.model_validate(r.json())
        assert (v2.version, v2.set_by, v2.reason) == (2, "local", "P1 stays below 0.2 V")
        assert c.post("/levels", json=[{"channel": "P1", "value": 0.1}]).status_code == 200
        v3 = StandState.model_validate(c.get("/stand/state").json())
        assert v3.version == 3 and [(lv.channel, lv.value) for lv in v3.held] == [("P1", 0.1)]
        assert v3.limits == v2.limits  # carried over
        assert "levels set: P1 = 0.1" in v3.reason
        r = c.post("/stand/state", json={"couplings": {"P1": {"P2": -0.2}}, "reason": "lever arms"})
        v4 = StandState.model_validate(r.json())
        assert (
            v4.couplings == {"P1": {"P2": -0.2}} and v4.held == v3.held and v4.limits == v2.limits
        )
        c.delete("/levels")
        history = [StandState.model_validate(s) for s in c.get("/stand-states").json()]
        assert [s.version for s in history] == [1, 2, 3, 4, 5]
        assert history[-1].held == () and "released" in history[-1].reason
        assert c.app.state.registry.stand_state(v4.stand_id) == history[-1]  # the registry's truth


def test_a_level_beyond_its_limit_is_refused_and_nothing_moves(tmp_path):
    with server(tmp_path / "registry") as c:
        c.post("/levels", json=[{"channel": "P1", "value": 0.05}])
        c.post("/stand/state", json={"limits": [limit("P1", -0.1, 0.2)], "reason": "limit P1"})
        version = c.get("/stand/state").json()["version"]
        r = c.post(
            "/levels", json=[{"channel": "P2", "value": 0.1}, {"channel": "P1", "value": 0.25}]
        )
        assert r.status_code == 400
        assert "P1 would reach 0.25, beyond its limit [-0.1, 0.2]" in r.json()["detail"]
        assert (
            setpoint(c, "P1") == 0.05 and setpoint(c, "P2") != 0.1
        )  # refused whole: P2 not set either
        assert c.get("/stand/state").json()["version"] == version  # nothing written
        assert [lv["value"] for lv in c.get("/levels").json()] == [0.05]
        assert (
            c.post("/levels", json=[{"channel": "P1", "value": 0.2}]).status_code == 200
        )  # inclusive


def test_a_sweep_beyond_a_limit_is_refused_at_compile_and_at_submission(tmp_path):
    with server(tmp_path / "registry") as c:
        c.post("/stand/state", json={"limits": [limit("P1", 0.0, 0.1)], "reason": "limit P1"})
        r = c.post("/sweeps/compile", json=definition())
        assert r.status_code == 400 and "P1 would reach 0.03 to 0.18" in r.json()["detail"]
        assert c.post("/runs", json={"definition": definition()}).status_code == 400
        assert c.get("/runs").json() == []  # never queued
        ok = c.post("/sweeps/compile", json=definition(p1=(0.0, 0.1)))
        assert ok.status_code == 200, ok.text
        assert ok.json()["definition"]["axes"][0]["stop"] == 0.1  # not clamped, not rewritten


def test_a_queued_run_is_checked_again_when_it_starts(tmp_path):
    """A limit tightened while a run waits in the queue still holds: the run fails, unrun."""
    with server(tmp_path / "registry") as c:
        runs = c.app.state.runs
        c.portal.call(runs._lock.acquire)  # a run in progress, as far as the queue can tell
        try:
            run = c.post("/runs", json={"definition": definition()}).json()
            assert run["state"] == "queued"
            r = c.post(
                "/stand/state", json={"limits": [limit("P1", 0.0, 0.1)], "reason": "tighter"}
            )
            assert r.status_code == 201
        finally:
            c.portal.call(runs._lock.release)
        done = wait_for(c, run["run_id"])
        assert done.state == "failed" and "P1 would reach 0.03 to 0.18" in done.error
        assert done.record_id is None


def test_new_limits_that_exclude_the_held_point_are_refused(tmp_path):
    with server(tmp_path / "registry") as c:
        c.post("/levels", json=[{"channel": "SG", "value": -0.04}])
        r = c.post("/stand/state", json={"limits": [limit("SG", 0.0, 0.5)], "reason": "too tight"})
        assert r.status_code == 400 and "held point is beyond its limits" in r.json()["detail"]
        assert c.get("/stand/state").json()["limits"] == []
        assert (
            c.post(
                "/stand/state", json={"limits": [limit("nope", 0, 1)], "reason": "x"}
            ).status_code
            == 400
        )
        scope = c.post("/stand/state", json={"limits": [limit("scope1", 0, 1)], "reason": "x"})
        assert scope.status_code == 400 and "drives no level" in scope.json()["detail"]
        off = c.post("/stand/state", json={"couplings": {"P1": {"scope1": 1.0}}, "reason": "x"})
        assert off.status_code == 400 and "not a LevelSource" in off.json()["detail"]
        assert c.post("/stand/state", json={"limits": [], "reason": ""}).status_code == 422


def test_after_a_restart_the_held_point_is_offered_and_applied_only_on_confirmation(tmp_path):
    root = tmp_path / "registry"
    with server(root) as c:
        c.post("/stand/state", json={"limits": [limit("P1", -0.1, 0.2)], "reason": "limit P1"})
        c.post(
            "/levels", json=[{"channel": "P1", "value": 0.12}, {"channel": "SG", "value": -0.04}]
        )
        before = c.get("/stand/state").json()
    with server(root) as c:  # the stand server restarts
        assert c.get("/stand/state").json() == before  # loaded, limits in force
        assert c.get("/levels").json() == []  # nothing held, nothing applied
        pending = {lv["channel"]: lv["value"] for lv in c.get("/levels/pending").json()}
        assert pending == {"P1": 0.12, "SG": -0.04}
        assert setpoint(c, "P1") != 0.12
        plan = c.post("/sweeps/compile", json=definition(p1=(0.0, 0.1))).json()
        assert plan["definition"].get("levels", []) == []  # a sweep inherits nothing yet
        refused = c.post("/levels", json=[{"channel": "P1", "value": 0.3}])
        assert refused.status_code == 400  # the limits are in force before confirmation
        held = c.post("/levels/pending/confirm")
        assert held.status_code == 200, held.text
        assert {lv["channel"]: lv["value"] for lv in held.json()} == pending
        assert setpoint(c, "P1") == 0.12 and c.get("/levels/pending").json() == []
        assert (
            c.get("/stand/state").json()["version"] == before["version"]
        )  # confirming changes nothing
        assert c.post("/levels/pending/confirm").status_code == 409
        plan = c.post("/sweeps/compile", json=definition(p1=(0.0, 0.1))).json()
        assert {lv["channel"] for lv in plan["definition"]["levels"]} == {"SG"}  # P1 is swept
    with server(root) as c:  # restarts again; this time the offer is declined
        assert c.delete("/levels/pending").status_code == 200
        after = StandState.model_validate(c.get("/stand/state").json())
        assert after.version == before["version"] + 1 and after.held == ()
        assert "not re-applied" in after.reason and after.limits[0].channel == "P1"
        assert c.delete("/levels/pending").status_code == 409


def test_setting_a_level_before_confirming_discards_the_offer_and_says_so(tmp_path):
    root = tmp_path / "registry"
    with server(root) as c:
        c.post(
            "/levels", json=[{"channel": "P1", "value": 0.12}, {"channel": "SG", "value": -0.04}]
        )
    with server(root) as c:
        c.post("/levels", json=[{"channel": "P2", "value": 0.07}])
        state = StandState.model_validate(c.get("/stand/state").json())
        assert [(lv.channel, lv.value) for lv in state.held] == [("P2", 0.07)]
        assert "(P1 = 0.12, SG = -0.04) was not re-applied" in state.reason
        assert c.get("/levels/pending").json() == []


def test_a_change_from_another_desk_is_recorded_under_its_tokens_label(tmp_path):
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    token = new_token(settings.token_file, "desk two")
    change = {"limits": [limit("P1", -0.1, 0.2)], "reason": "from the second desk"}
    with TestClient(create_app(settings), client=ELSEWHERE) as c:
        assert c.get("/stand/state").status_code == 200  # a read
        assert c.post("/stand/state", json=change).status_code == 401
        assert c.post("/levels/pending/confirm").status_code == 401
        assert c.delete("/levels/pending").status_code == 401
        r = c.post("/stand/state", json=change, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201 and r.json()["set_by"] == "desk two"


def test_a_rebuilt_stand_server_continues_the_history_on_the_registry_server(tmp_path, monkeypatch):
    """ADR 0085: a stand server with a new cache takes the stand's versions from the registry server
    at start, so the limits stay in force and its next version follows the server's latest."""
    (tmp_path / "server").mkdir()
    monkeypatch.setenv(DSN_ENV, f"sqlite:///{(tmp_path / 'server' / 'server.sqlite').as_posix()}")
    monkeypatch.setenv(STORE_ENV, str(tmp_path / "server" / "store"))
    with server(tmp_path / "old-pc") as c:
        c.post("/stand/state", json={"limits": [limit("P1", -0.1, 0.2)], "reason": "limit P1"})
        registry = c.app.state.registry
        t0 = time.monotonic()
        while registry.unsynced()["stand_states"] and time.monotonic() - t0 < 10:
            c.portal.call(c.app.state.runs.sync)
    with server(tmp_path / "new-pc") as c:
        state = StandState.model_validate(c.get("/stand/state").json())
        assert state.version == 2 and state.limit("P1") is not None
        assert c.post("/levels", json=[{"channel": "P1", "value": 0.3}]).status_code == 400
        c.post("/levels", json=[{"channel": "P1", "value": 0.1}])
        assert c.get("/stand/state").json()["version"] == 3
        c.portal.call(c.app.state.runs.sync)
    remote = Registry(
        tmp_path / "reader",
        remote_dsn=f"sqlite:///{(tmp_path / 'server' / 'server.sqlite').as_posix()}",
    )
    assert [s.version for s in remote.stand_states(remote=True)] == [1, 2, 3]
