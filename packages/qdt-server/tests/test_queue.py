"""The run queue in the stand server (ADR 0075, 0086; Step 6c L0 row "Queue"): order holds through
reorder, remove and abort; a queued entry survives a server restart; one run at a time."""

import itertools
import time

from fastapi.testclient import TestClient

from qdt_schemas.operations import StandQueue
from qdt_server import Settings, create_app
from qdt_server.auth import new_token
from qdt_sim.scenarios import stability

LOOPBACK = ("127.0.0.1", 50000)
ELSEWHERE = ("192.0.2.10", 50000)
"""Another computer: a documentation address (RFC 5737 TEST-NET-1), no real desk (rule 7)."""


def request(name: str, n: int = 6) -> dict:
    sweep = stability(n, n, p1=(0.03, 0.18), p2=(0.03, 0.18), name=name)
    return {"definition": sweep.model_dump(mode="json"), "options": {"seed": 1}}


def server(root, **kw) -> TestClient:
    return TestClient(create_app(Settings(root=root, stream_port=0, **kw)), client=LOOPBACK)


def view(c) -> StandQueue:
    return StandQueue.model_validate(c.get("/queue").json())


def until(c, condition, timeout: float = 30.0) -> StandQueue:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        q = view(c)
        if condition(q):
            return q
        time.sleep(0.05)
    raise TimeoutError(view(c).model_dump_json(indent=1))


def names(entries) -> list[str]:
    return [e.request.definition.name for e in entries]


def test_order_holds_through_reorder_and_remove_and_records_land_in_the_final_order(tmp_path):
    with server(tmp_path / "registry") as c:
        assert view(c).paused is False and view(c).entries == ()
        c.post("/queue/pause")  # held, so the order can be arranged before anything starts
        ids = [c.post("/queue", json=request(n)).json()["queue_id"] for n in ("a", "b", "c", "d")]
        q = view(c)
        assert q.paused and names(q.entries) == ["a", "b", "c", "d"]
        assert [e.position for e in q.entries] == [0, 1, 2, 3]
        assert {e.submitted_by for e in q.entries} == {"local"}
        assert names(
            StandQueue.model_validate(
                c.post(f"/queue/{ids[3]}/move", json={"position": 0}).json()
            ).entries
        ) == ["d", "a", "b", "c"]
        assert names(StandQueue.model_validate(c.delete(f"/queue/{ids[1]}").json()).entries) == [
            "d",
            "a",
            "c",
        ]
        c.post("/queue/resume")
        q = until(c, lambda q: all(e.state == "done" for e in q.entries) and len(q.entries) == 3)
        done = sorted(q.entries, key=lambda e: e.finished_at)
        assert names(done) == ["d", "a", "c"]  # they ran in the final order; "b" never ran
        records = [c.app.state.registry.get(e.record_id) for e in done]
        assert [r.definition_name for r in records] == ["d", "a", "c"]
        assert [r.started_at for r in records] == sorted(r.started_at for r in records)
        assert [r["definition_name"] for r in c.get("/records").json()] == ["d", "a", "c"]


def test_a_running_entry_is_aborted_and_the_queue_goes_on(tmp_path):
    with server(tmp_path / "registry") as c:
        runs = c.app.state.runs
        c.portal.call(
            runs._lock.acquire
        )  # the stand is busy: the first entry runs but cannot start frames
        try:
            first = c.post("/queue", json=request("first")).json()["queue_id"]
            second = c.post("/queue", json=request("second")).json()["queue_id"]
            q = until(c, lambda q: q.entries[0].state == "running" and q.entries[0].run_id)
            assert names(q.entries) == ["first", "second"] and q.entries[1].position == 0
            assert c.post(f"/queue/{second}/abort").status_code == 409  # a waiting entry is removed
            assert c.post(f"/queue/{first}/move", json={"position": 0}).status_code == 409
            assert c.delete(f"/queue/{first}").status_code == 409
            assert c.post(f"/queue/{first}/abort").status_code == 200
        finally:
            c.portal.call(runs._lock.release)
        q = until(c, lambda q: not any(e.state in ("queued", "running") for e in q.entries))
        by_name = {e.request.definition.name: e for e in q.entries}
        assert by_name["first"].state == "aborted" and by_name["first"].record_id is None
        assert by_name["second"].state == "done" and by_name["second"].record_id


def test_one_run_at_a_time_with_the_queue_and_a_direct_run(tmp_path):
    with server(tmp_path / "registry") as c:
        for n in ("q1", "q2"):
            c.post("/queue", json=request(n, n=10))
        direct = c.post("/runs", json=request("direct", n=10)).json()["run_id"]
        until(c, lambda q: sum(e.state == "done" for e in q.entries) == 2)
        t0 = time.monotonic()
        while (
            c.get(f"/runs/{direct}").json()["state"] in ("queued", "running")
            and time.monotonic() - t0 < 30
        ):
            time.sleep(0.05)
        spans = sorted((r["started_at"], r["finished_at"]) for r in c.get("/runs").json())
        assert len(spans) == 3
        assert all(a[1] <= b[0] for a, b in itertools.pairwise(spans))  # no two overlap


def test_waiting_entries_survive_a_restart_and_wait_for_a_person_to_resume(tmp_path):
    root = tmp_path / "registry"
    with server(root) as c:
        runs = c.app.state.runs
        c.portal.call(runs._lock.acquire)
        c.post("/queue", json=request("interrupted"))
        until(c, lambda q: q.entries and q.entries[0].state == "running")
        for n in ("x", "y"):
            c.post("/queue", json=request(n))
        c.post(f"/queue/{view(c).entries[2].queue_id}/move", json={"position": 0})  # y before x
        # the server stops with one entry running and two waiting (the lock is never released)
    with server(root) as c:
        q = view(c)
        assert q.paused and "restarted with 2 entries waiting" in q.note
        assert names(e for e in q.entries if e.state == "queued") == ["y", "x"]
        [stopped] = [e for e in q.entries if e.request.definition.name == "interrupted"]
        assert stopped.state == "aborted" and "stopped while this entry ran" in stopped.message
        time.sleep(0.3)
        assert all(e.state != "running" for e in view(c).entries)  # nothing starts unasked
        c.post("/queue/resume")
        q = until(c, lambda q: sum(e.state == "done" for e in q.entries) == 2)
        assert names(
            sorted((e for e in q.entries if e.state == "done"), key=lambda e: e.finished_at)
        ) == ["y", "x"]
    with server(root) as c:  # nothing waits now: the queue is not paused after this restart
        assert view(c).paused is False


def test_refusals_and_who_submitted_from_another_desk(tmp_path):
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    token = new_token(settings.token_file, "desk two")
    with TestClient(create_app(settings), client=LOOPBACK) as c:
        c.post(
            "/stand/state",
            json={"limits": [{"channel": "P1", "min_v": 0.0, "max_v": 0.1}], "reason": "limit P1"},
        )
        r = c.post("/queue", json=request("too far"))
        assert r.status_code == 400 and "P1 would reach 0.03 to 0.18" in r.json()["detail"]
        assert view(c).entries == ()  # refused before it waits
        c.post("/queue/pause")
        bad = request("nope")
        bad["definition"]["axes"][0]["channel"] = "nope"
        assert c.post("/queue", json=bad).status_code == 400
        ok = request("ok")
        ok["definition"]["axes"][0].update(start=0.0, stop=0.1)
        entry = c.post("/queue", json=ok).json()["queue_id"]
        assert (
            c.post(f"/queue/{entry}/move", json={"position": 1}).status_code == 400
        )  # one waiting
        assert c.delete("/queue/" + "0" * 32).status_code == 404
        assert c.post("/queue/" + "0" * 32 + "/abort").status_code == 404
    with TestClient(create_app(settings), client=ELSEWHERE) as c:
        assert c.get("/queue").status_code == 200  # a read
        assert c.post("/queue", json=ok).status_code == 401
        assert c.post("/queue/resume").status_code == 401
        assert c.delete(f"/queue/{entry}").status_code == 401
        r = c.post("/queue", json=ok, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201 and r.json()["submitted_by"] == "desk two"


def test_an_error_in_the_worker_pauses_the_queue_and_says_why(tmp_path, monkeypatch):
    """Never a silent stop: if keeping an entry fails (a full disk, say), the queue pauses with the error."""
    with server(tmp_path / "registry") as c:
        c.post("/queue/pause")
        c.post("/queue", json=request("doomed"))
        registry = c.app.state.registry

        def broken(*entries):
            raise OSError("no space left on device")

        monkeypatch.setattr(registry, "queue_put", broken)
        c.post("/queue/resume")
        q = until(c, lambda q: q.paused)
        assert "the queue stopped on an error: no space left on device" in q.note
