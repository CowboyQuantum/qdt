"""The Step 4b loop over the API against the simulator: compile, run, stream, record, analyse, replay."""

import asyncio
import time
from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from qdt_lab.stream import collect
from qdt_schemas.activity import SweepDefinition
from qdt_schemas.control import Run
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult
from qdt_server import Settings, create_app
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


def test_diamonds_run_through_the_api_with_a_cold_sensor(client):
    d = diamonds(64, 64, name="api diamonds").model_dump(mode="json")
    options = {"noise": False, "sensor_width_v": 0.01, "seed": 2}  # a model field as a run option
    run = Run.model_validate(
        client.post("/runs", json={"definition": d, "options": options}).json()
    )
    run = wait_for(client, run.run_id)
    assert run.state == "completed", run.error
    assert run.attrs["sensor_width_v"] == 0.01
    assert SweepDefinition.model_validate(d).sensed[0].name == "I_sensor"
    r = client.post(
        f"/records/{run.record_id}/results",
        json={"method": "qdt_analysis.diamonds.detect_diamonds"},
    )
    assert r.status_code == 201, r.text
    result = AnalysisResult.model_validate(r.json())
    assert result.status == "ok", result.message
    assert result.estimate("charging_energy").value == pytest.approx(1e-3, rel=0.05)


def edited(outer: bool = True) -> dict:
    """What Flight Deck's sequence editor sends beyond the template: a ramp with a symbol duration, a
    wait, a kick on the bias line bound to a constant or the stepped axis, two measures, shots reduced."""
    v = lambda name, unit="V": {"name": name, "unit": unit}
    axes = [{"name": "P2", "channel": "P2_pulse", "start": 0.03, "stop": 0.18, "num": 8}]
    if outer:
        axes.insert(0, {"name": "P1", "channel": "P1", "start": 0.03, "stop": 0.18, "num": 6})
    body = [
        {
            "op": "ramp",
            "channel": "P2_pulse",
            "start": 0.0,
            "stop": v("v_P2"),
            "duration": v("t_ramp", "ns"),
        },
        {"op": "wait", "duration": 200},
        {"op": "measure", "channel": "sensor", "duration": 1000, "result": "I_before"},
        {"op": "step", "channel": "bias_pulse", "level": v("v_kick"), "duration": 100},
        {"op": "measure", "channel": "sensor", "duration": 1000, "result": "I_after"},
    ]
    kick = {"symbol": "v_kick", "axis": "P1"} if outer else {"symbol": "v_kick", "value": 1e-4}
    return {
        "name": "edited sequence",
        "axes": axes,
        "stage": {
            "instrument": "dot",
            "axes": ["P2"],
            "sequence": {"name": "pulsed readout", "body": body},
            "bindings": [{"symbol": "v_P2", "axis": "P2"}, {"symbol": "t_ramp", "value": 40}, kick],
            "shots": 3,
            "reduce": {"I_before": "mean", "I_after": "mean"},
        },
    }


@pytest.mark.parametrize("outer", [True, False], ids=["2-D", "1-D"])
def test_an_edited_sequence_compiles_and_runs(client, outer):
    plan = client.post("/sweeps/compile", json=edited(outer))
    assert plan.status_code == 200, plan.text
    dataset = plan.json()["dataset"]
    assert [d["name"] for d in dataset["dims"]] == (["P1", "P2"] if outer else ["P2"])
    assert sorted(v["name"] for v in dataset["data_vars"]) == ["I_after", "I_before"]
    run = Run.model_validate(client.post("/runs", json={"definition": edited(outer)}).json())
    run = wait_for(client, run.run_id)
    assert run.state == "completed" and run.record_id, run.error


def test_a_1d_dc_sweep_runs(client):
    d = {
        "name": "SG trace",
        "axes": [{"name": "SG", "channel": "SG", "start": -0.2, "stop": 0.2, "num": 16}],
        "sensed": [{"name": "I_sensor", "channel": "sensor"}],
    }
    run = Run.model_validate(client.post("/runs", json={"definition": d}).json())
    run = wait_for(client, run.run_id)
    assert run.state == "completed" and run.record_id, run.error


def test_the_browser_may_call_from_another_origin(client):
    r = client.options(
        "/runs",
        headers={
            "origin": "http://127.0.0.1:5173",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    r = client.get("/stand", headers={"origin": "http://127.0.0.1:5173"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_a_built_ui_is_served_beside_the_api(tmp_path, client):
    assert client.get("/").status_code == 404  # no UI unless asked for
    ui = tmp_path / "dist"
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<title>Flight Deck</title>")
    (ui / "assets" / "app.js").write_text("// app")
    app = create_app(Settings(root=tmp_path / "registry2", stream_port=0, ui=ui))
    with TestClient(app) as c:
        assert "Flight Deck" in c.get("/").text
        assert c.get("/assets/app.js").text == "// app"
        assert c.get("/stand").json()["stand_id"] == "simulated-double-dot"  # API routes first


def test_a_run_can_be_aborted_queued_or_running(tmp_path):
    from qdt_server.app import simulated_backends

    def slow(options):  # 1024 pixels at 400 px/s: long enough to catch it running
        backends = simulated_backends(options)
        for device in backends.values():
            device.points_per_second = 400.0
        return backends

    app = create_app(Settings(root=tmp_path / "registry", stream_port=0, backends=slow))
    with TestClient(app) as c:
        first = Run.model_validate(c.post("/runs", json={"definition": definition()}).json())
        queued = Run.model_validate(c.post("/runs", json={"definition": definition()}).json())

        r = c.post(f"/runs/{queued.run_id}/abort")
        assert r.status_code == 202 and r.json()["state"] == "aborted"

        t0 = time.monotonic()
        while c.get(f"/runs/{first.run_id}").json()["state"] == "queued":
            assert time.monotonic() - t0 < 10
            time.sleep(0.02)
        time.sleep(0.3)  # a few lines in
        assert c.post(f"/runs/{first.run_id}/abort").status_code == 202
        run = wait_for(c, first.run_id)
        assert run.state == "aborted" and run.record_id, run.error
        record = MeasurementRecord.model_validate(c.get(f"/records/{run.record_id}").json())
        assert record.outcome == "aborted"

        assert c.post(f"/runs/{first.run_id}/abort").status_code == 409
        assert c.post("/runs/" + "0" * 32 + "/abort").status_code == 404
        # the queued one never ran and recorded nothing
        assert Run.model_validate(c.get(f"/runs/{queued.run_id}").json()).record_id is None
        assert [r["record_id"] for r in c.get("/records").json()] == [record.record_id]


def test_a_chopped_readout_records_the_difference(client):
    """ADR 0037: the chop point follows the swept level (an Affine), and the sequencer subtracts the two
    measures per shot into a result of its own, recorded beside them."""
    d = edited()
    v = {"name": "v_P2", "unit": "V"}
    d["stage"]["sequence"]["body"] = [
        {"op": "step", "channel": "P2_pulse", "level": v, "duration": 500},
        {"op": "measure", "channel": "sensor", "duration": 1000, "result": "I_on"},
        {
            "op": "step",
            "channel": "P2_pulse",
            "level": {"symbol": v, "offset": 0.002},
            "duration": 500,
        },
        {"op": "measure", "channel": "sensor", "duration": 1000, "result": "I_off"},
        {"op": "difference", "result": "dI", "a": "I_on", "b": "I_off"},
    ]
    d["stage"]["bindings"] = [{"symbol": "v_P2", "axis": "P2"}]
    d["stage"]["reduce"] = {"I_on": "mean", "I_off": "mean", "dI": "mean"}
    plan = client.post("/sweeps/compile", json=d)
    assert plan.status_code == 200, plan.text
    assert sorted(x["name"] for x in plan.json()["dataset"]["data_vars"]) == ["I_off", "I_on", "dI"]
    run = Run.model_validate(client.post("/runs", json={"definition": d}).json())
    run = wait_for(client, run.run_id)
    assert run.state == "completed" and run.record_id, run.error
    d["stage"]["sequence"]["body"][-1]["b"] = "I_nope"
    bad = client.post("/sweeps/compile", json=d)
    assert bad.status_code == 422 and "measured earlier" in bad.text


def test_a_sweep_runs_on_the_real_drivers_streams_and_records(tmp_path):
    """Step 5: the server on a stand of real drivers (here over their SCPI emulators): a QDAC-II gate
    stepped outside, a Keithley sourcing V and sensing I on its one terminal inside. The record holds
    the I-V line of the emulator's 1 MOhm load."""
    from qdt_lab.drivers.keithley.k2400_emulator import emulated as k2400
    from qdt_lab.drivers.qdevil.qdac2_emulator import emulated as qdac2
    from qdt_schemas.identity import DeviceRecord
    from qdt_schemas.payload_hdf5 import read_payload
    from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

    stand = StandConfig(
        stand_id="bench",
        instruments=(
            InstrumentConfig(id="dac0", backend="qdac2", capabilities=("level_source",)),
            InstrumentConfig(
                id="smu", backend="keithley2400", capabilities=("level_source", "level_sense")
            ),
        ),
        channels=(
            ChannelMap(logical="P1", instrument="dac0", channel="ch01", quantity="voltage"),
            ChannelMap(logical="smu_v", instrument="smu", channel="out", quantity="voltage"),
            ChannelMap(logical="smu_i", instrument="smu", channel="out_i", quantity="current"),
        ),
    )
    device = DeviceRecord(
        device_id="dut-1",
        kind="device",
        simulated=False,
        registered_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    built = {
        "dac0": qdac2(stand.instrument_channels("dac0")),
        "smu": k2400("2450", stand.instrument_channels("smu")),
    }
    settings = Settings(
        root=tmp_path / "registry",
        stream_port=0,
        stand=stand,
        device=device,
        backends=lambda o: built,
    )
    d = {
        "name": "iv on drivers",
        "axes": [
            {"name": "P1", "channel": "P1", "start": 0.0, "stop": 0.1, "num": 2},
            {"name": "V", "channel": "smu_v", "start": -1.0, "stop": 1.0, "num": 5},
        ],
        "sensed": [{"name": "I", "channel": "smu_i"}],
    }
    with TestClient(create_app(settings)) as c:
        run = wait_for(c, Run.model_validate(c.post("/runs", json={"definition": d}).json()).run_id)
        assert run.state == "completed" and run.record_id, run.error
        record = MeasurementRecord.model_validate(c.get(f"/records/{run.record_id}").json())
        assert record.device_id == "dut-1" and record.stand_id == "bench"
        payload = read_payload(tmp_path / "registry" / "payloads" / record.payload.path)
    np.testing.assert_allclose(
        payload.arrays["I"], np.tile(np.linspace(-1, 1, 5) / 1e6, (2, 1)), rtol=1e-9
    )
    assert built["dac0"].get("ch01") == 0.1  # the outer gate was really stepped through the driver


def test_a_restarted_server_reuses_its_registered_device(tmp_path):
    """A second start registers the same device id at a later time; the registry would call a
    differing body a conflict, so the server keeps the existing registration."""
    import dataclasses
    from datetime import UTC, datetime

    from qdt_schemas.identity import DeviceRecord

    root = tmp_path / "registry"
    first = Settings(root=root, stream_port=0)
    later = dataclasses.replace(
        first,
        device=DeviceRecord(
            device_id=first.device.device_id,
            kind=first.device.kind,
            simulated=first.device.simulated,
            registered_at=datetime(2030, 1, 1, tzinfo=UTC),
        ),
    )
    with TestClient(create_app(first)) as c:
        assert c.get("/devices").status_code == 200
    with TestClient(create_app(later)) as c:
        assert [d["device_id"] for d in c.get("/devices").json()] == [first.device.device_id]
    other_kind = dataclasses.replace(
        first,
        device=DeviceRecord(
            device_id=first.device.device_id,
            kind="device",
            simulated=False,
            registered_at=datetime(2030, 1, 1, tzinfo=UTC),
        ),
    )
    with pytest.raises(ValueError, match="registered as"), TestClient(create_app(other_kind)):
        pass
