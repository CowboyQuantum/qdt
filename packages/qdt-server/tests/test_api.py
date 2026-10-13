"""The Step 4b loop over the API against the simulator: compile, run, stream, record, analyse, replay."""

import asyncio
import time

from qdt_lab.stream import collect
from qdt_schemas.activity import SweepDefinition
from qdt_schemas.control import Run
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult
from qdt_sim.scenarios import DEVICE_ID, diamonds, stability


def definition(n=(32, 32)) -> dict:
    return stability(*n, p1=(0.03, 0.18), p2=(0.03, 0.18), name="api stability").model_dump(
        mode="json"
    )


def wait_for(client, run_id: str, timeout: float = 30.0) -> Run:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        run = Run.model_validate(client.get(f"/runs/{run_id}").json())
        if run.state not in ("queued", "running"):
            return run
        time.sleep(0.05)
    raise TimeoutError(run_id)


def test_stand_devices_and_stream_are_described(client):
    assert client.get("/stand").json()["stand_id"] == "simulated-double-dot"
    assert [d["device_id"] for d in client.get("/devices").json()] == [DEVICE_ID]
    assert client.get("/stream").json()["url"].startswith("ws://127.0.0.1:")


def test_compile_returns_a_plan_or_a_400(client):
    r = client.post("/sweeps/compile", json=definition())
    assert r.status_code == 200 and r.json()["dataset"]["dims"][0]["name"] == "P1"
    bad = definition()
    bad["axes"][0]["channel"] = "nope"
    r = client.post("/sweeps/compile", json=bad)
    assert r.status_code == 400 and "nope" in r.json()["detail"]
    assert client.post("/sweeps/compile", json={"name": "x"}).status_code == 422


def test_a_run_streams_records_and_can_be_analysed(client):
    r = client.post(
        "/runs", json={"definition": definition(), "options": {"seed": 1, "campaign": "t"}}
    )
    assert r.status_code == 202
    run = Run.model_validate(r.json())
    assert run.state == "queued" and run.device_id == DEVICE_ID
    url = client.get("/stream").json()["url"]
    received = asyncio.run(collect(url, timeout=30))
    assert run.plan_id in received and received[run.plan_id].complete
    run = wait_for(client, run.run_id)
    assert run.state == "completed" and run.record_id, run.error
    assert [r["run_id"] for r in client.get("/runs").json()] == [run.run_id]

    record = MeasurementRecord.model_validate(client.get(f"/records/{run.record_id}").json())
    assert record.plan_id == run.plan_id and record.campaign == "t"
    assert [r["record_id"] for r in client.get("/records", params={"campaign": "t"}).json()] == [
        record.record_id
    ]
    assert client.get("/records", params={"campaign": "other"}).json() == []

    methods = client.get("/methods").json()
    name = next(m["name"] for m in methods if m["title"] == "Charge transitions")
    r = client.post(
        f"/records/{record.record_id}/results",
        json={"method": name, "parameters": {"smooth_px": 1.2}},
    )
    assert r.status_code == 201, r.text
    result = AnalysisResult.model_validate(r.json())
    assert result.record_id == record.record_id and result.method.parameters["smooth_px"] == 1.2
    assert result.output is not None  # the detection map, stored by the server
    assert [
        x["result_id"]
        for x in client.get("/results", params={"record_id": record.record_id}).json()
    ] == [result.result_id]
    assert client.get(f"/results/{result.result_id}").json()["result_id"] == result.result_id

    bad = client.post(
        f"/records/{record.record_id}/results",
        json={"method": name, "parameters": {"smooth_px": -1}},
    )
    assert bad.status_code == 400 and "minimum" in bad.json()["detail"]
    assert (
        client.post(f"/records/{record.record_id}/results", json={"method": "nope"}).status_code
        == 404
    )

    # the record's Dataset is already on the stream (it ran live): replay publishes just the overlays;
    # a result's output is a new Dataset. `collect` stops at the last final chunk, so the output replay
    # goes second and the overlays, published before it, are read on the way.
    assert client.post("/stream/replay", json={"record_id": record.record_id}).status_code == 202
    assert client.post("/stream/replay", json={"result_id": result.result_id}).status_code == 202
    received = asyncio.run(collect(url, n_datasets=2, timeout=30))
    assert {a.annotation_id for a in received[run.plan_id].annotations} == {
        a.annotation_id for a in result.annotations
    }
    assert any(
        d.dataset.source.kind == "registry" and d.dataset.source.registry_ref == result.result_id
        for d in received.values()
    )
    assert client.post("/stream/replay", json={"result_id": result.result_id}).status_code == 409


def test_a_failing_run_says_why(client):
    bad = definition()
    bad["axes"][0]["channel"] = "nope"
    assert client.post("/runs", json={"definition": bad}).status_code == 400
    assert client.get("/runs/" + "0" * 32).status_code == 404
    assert client.get("/records/" + "0" * 32).status_code == 404
    assert client.get("/results/" + "0" * 32).status_code == 404


def test_diamonds_run_through_the_api(client):
    d = diamonds(24, 24, name="api diamonds").model_dump(mode="json")
    run = Run.model_validate(
        client.post("/runs", json={"definition": d, "options": {"noise": False}}).json()
    )
    run = wait_for(client, run.run_id)
    assert run.state == "completed", run.error
    assert SweepDefinition.model_validate(d).sensed[0].name == "I_sensor"
    r = client.post(
        f"/records/{run.record_id}/results",
        json={"method": "qdt_analysis.diamonds.detect_diamonds"},
    )
    assert r.status_code == 201 and r.json()["status"] in ("ok", "failed")
