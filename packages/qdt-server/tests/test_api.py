"""The Step 4b loop over the API against the simulator: compile, run, stream, record, analyse, replay."""

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from qdt_lab.stream import collect
from qdt_registry import DSN_ENV, STORE_ENV, Registry
from qdt_schemas.activity import SweepDefinition
from qdt_schemas.control import Run
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult
from qdt_server import Settings, create_app
from qdt_sim.scenarios import DEVICE_ID, diamonds, stability

LOOPBACK = ("127.0.0.1", 50000)
"""The test client's peer: this computer, so commands need no token (ADR 0074). The default peer,
`testclient`, is not an address and counts as another computer."""


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
    with TestClient(app, client=LOOPBACK) as c:
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
    with TestClient(app, client=LOOPBACK) as c:
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
    with TestClient(create_app(settings), client=LOOPBACK) as c:
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
    with TestClient(create_app(first), client=LOOPBACK) as c:
        assert c.get("/devices").status_code == 200
    with TestClient(create_app(later), client=LOOPBACK) as c:
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
    with pytest.raises(ValueError, match="registered as"), TestClient(create_app(other_kind), client=LOOPBACK):
        pass


def test_a_capture_runs_through_the_server_and_the_exponential_reads_its_droop(client):
    """ADR 0047: the L0 model of L2-3. The simulated scope records a droop (a step of `droop_v` at
    t = 0 decaying with `tau_s`); the capture streams, is recorded, and the single exponential recovers
    τ from the stored record through the same API Flight Deck uses."""
    stand = client.get("/stand").json()
    scope = next(i for i in stand["instruments"] if "waveform_sense" in i["capabilities"])
    assert any(c["instrument"] == scope["id"] for c in stand["channels"])
    definition = {
        "name": "api droop",
        "captured": [
            {
                "name": "trace",
                "channel": "scope1",
                "start_s": -1e-3,
                "stop_s": 9e-3,
                "num": 1000,
                "records": 2,
            }
        ],
    }
    plan = client.post("/sweeps/compile", json=definition)
    assert plan.status_code == 200, plan.text
    assert [d["name"] for d in plan.json()["dataset"]["dims"]] == ["record", "time"]
    options = {"seed": 3, "tau_s": 1.5e-3, "droop_v": 0.3, "scope_noise_v": 1e-3}
    run = Run.model_validate(
        client.post("/runs", json={"definition": definition, "options": options}).json()
    )
    run = wait_for(client, run.run_id)
    assert run.state == "completed", run.error
    r = client.post(
        f"/records/{run.record_id}/results",
        json={"method": "qdt_analysis.exponential.fit_exponential", "parameters": {}},
    )
    assert r.status_code == 201, r.text
    result = AnalysisResult.model_validate(r.json())
    assert result.status == "ok", result.message
    tau = result.estimate("tau")
    assert tau.value == pytest.approx(1.5e-3, rel=0.02) and tau.unit == "s"
    assert result.estimate("offset").value == pytest.approx(0.0, abs=2e-3)
    assert {a.kind for a in result.annotations} == {"marker"}
    assert result.output is not None
    # the plane fit does not apply to a trace and says so
    bad = client.post(
        f"/records/{run.record_id}/results", json={"method": "qdt_analysis.plane.fit_plane"}
    )
    assert bad.status_code == 400 and "linear coordinates" in bad.json()["detail"]


def test_level_state_reports_setpoints_held_levels_and_readbacks(client):
    """ADR 0057: GET /levels/state lists every channel an instrument sets or senses, with the level the
    instrument reports, the level the server holds, and a readback where the instrument senses the
    channel (the simulated device senses its sensor, never a gate: readback None there)."""
    rows = {r["channel"]: r for r in client.get("/levels/state").json()}
    assert "P1" in rows and "sensor" in rows and "scope1" not in rows  # the scope sets no level
    assert rows["P1"]["quantity"] == "voltage" and rows["P1"]["held"] is None
    assert rows["P1"]["readback"] is None  # a simulated gate refuses to be sensed
    assert isinstance(rows["sensor"]["readback"], float)  # the sensor current at the operating point
    client.post("/levels", json=[{"channel": "P1", "value": 0.05}])
    rows = {r["channel"]: r for r in client.get("/levels/state").json()}
    assert rows["P1"]["held"] == 0.05 and rows["P1"]["setpoint"] == 0.05  # set now, read back later
    before = rows["sensor"]["readback"]
    client.post("/levels", json=[{"channel": "P1", "value": 0.12}])
    rows = {r["channel"]: r for r in client.get("/levels/state").json()}
    assert rows["P1"]["setpoint"] == 0.12
    assert rows["sensor"]["readback"] != before  # the live device moved with the gate
    client.delete("/levels")
    rows = {r["channel"]: r for r in client.get("/levels/state").json()}
    assert rows["P1"]["held"] is None and rows["P1"]["setpoint"] == 0.12  # released, not zeroed


def test_the_server_holds_an_operating_point_that_sweeps_inherit(client):
    """ADR 0053 (click-to-set): POST /levels sets channels on the stand now and holds them; a compiled
    sweep carries them unless it moves the channel itself; DELETE releases them."""
    assert client.get("/levels").json() == []
    r = client.post(
        "/levels", json=[{"channel": "P1", "value": 0.05}, {"channel": "SG", "value": -0.04}]
    )
    assert r.status_code == 200, r.text
    assert [(lv["channel"], lv["value"]) for lv in r.json()] == [("P1", 0.05), ("SG", -0.04)]
    # merged, not replaced
    merged = client.post("/levels", json=[{"channel": "P2", "value": 0.1}]).json()
    assert [lv["channel"] for lv in merged] == ["P1", "P2", "SG"]
    assert client.get("/levels").json()[1]["value"] == 0.1
    # the stability sweep steps P1 and pulses P2_pulse: it inherits SG and the P2 DC line, not P1
    plan = client.post("/sweeps/compile", json=definition()).json()
    held = {lv["channel"]: lv["value"] for lv in plan["definition"].get("levels", [])}
    assert held == {"P2": 0.1, "SG": -0.04}
    # a run carries the merged operating point in the definition it records (its hash differs)
    run = Run.model_validate(client.post("/runs", json={"definition": definition((8, 8))}).json())
    run = wait_for(client, run.run_id)
    assert run.state == "completed", run.error
    assert (
        run.definition_sha256 != SweepDefinition.model_validate(definition((8, 8))).content_sha256()
    )
    # refusals: an unknown channel, a channel that is not a LevelSource
    assert client.post("/levels", json=[{"channel": "nope", "value": 0.0}]).status_code == 400
    bad = client.post("/levels", json=[{"channel": "scope1", "value": 0.0}])
    assert bad.status_code == 400 and "LevelSource" in bad.json()["detail"]
    assert client.delete("/levels").json() == [] and client.get("/levels").json() == []
    plan = client.post("/sweeps/compile", json=definition()).json()
    assert plan["definition"].get("levels", []) == []


def test_a_step_and_its_capture_compose_one_shot_through_the_server(client):
    """ADR 0060: L2-3 as a shot. The stimulus is a step on the device's pulse line, the readout a
    window on the simulated scope opened in the same shot; the trace is recorded like any result and
    the single exponential reads its droop from the stored record."""
    definition = {
        "name": "api step response",
        "stage": {
            "instrument": DEVICE_ID,
            "sequence": {
                "name": "step response",
                "body": [
                    {"op": "step", "channel": "P2_pulse", "level": 0.1, "duration": 2000},
                    {"op": "capture", "channel": "scope1", "duration": 8_000_000, "num": 800, "result": "trace"},
                ],
            },
            "shots": 1,
        },
    }
    plan = client.post("/sweeps/compile", json=definition)
    assert plan.status_code == 200, plan.text
    assert [d["name"] for d in plan.json()["dataset"]["dims"]] == ["time"]
    assert plan.json()["dataset"]["coords"][0]["start"] == 0.0
    options = {"seed": 3, "tau_s": 1.5e-3, "droop_v": 0.3, "scope_noise_v": 1e-3}
    run = Run.model_validate(
        client.post("/runs", json={"definition": definition, "options": options}).json()
    )
    run = wait_for(client, run.run_id)
    assert run.state == "completed", run.error
    r = client.post(
        f"/records/{run.record_id}/results",
        json={"method": "qdt_analysis.exponential.fit_exponential", "parameters": {}},
    )
    assert r.status_code == 201, r.text
    result = AnalysisResult.model_validate(r.json())
    assert result.status == "ok", result.message
    assert result.estimate("tau").value == pytest.approx(1.5e-3, rel=0.02)


# --- the registry server (ADR 0080): every record is offered to it; the cache keeps what it refuses ---


def _server_env(monkeypatch, tmp_path):
    """A SQLite file standing in for the server: its directory missing means the server is down."""
    dsn = f"sqlite:///{(tmp_path / 'server' / 'server.sqlite').as_posix()}"
    store = tmp_path / "server" / "store"
    monkeypatch.setenv(DSN_ENV, dsn)
    monkeypatch.setenv(STORE_ENV, str(store))
    return dsn, store


def _until(condition, timeout: float = 10.0) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if condition():
            return True
        time.sleep(0.05)
    return False


def _records_on_the_server(tmp_path, dsn) -> list[MeasurementRecord]:
    """As another computer would read them: a fresh client with only the server's address."""
    return Registry(tmp_path / "another-computer", remote_dsn=dsn).find(remote=True)


def test_a_record_reaches_the_registry_server_after_its_run(tmp_path, monkeypatch):
    dsn, store = _server_env(monkeypatch, tmp_path)
    (tmp_path / "server").mkdir()
    with TestClient(create_app(Settings(root=tmp_path / "registry", stream_port=0)), client=LOOPBACK) as c:
        run = wait_for(c, c.post("/runs", json={"definition": definition()}).json()["run_id"])
        assert run.state == "completed" and run.record_id, run.error
        assert _until(lambda: c.app.state.registry.unsynced()["records"] == 0)
    [remote] = _records_on_the_server(tmp_path, dsn)
    assert remote.record_id == run.record_id
    assert hashlib.sha256((store / remote.payload.path).read_bytes()).hexdigest() == remote.payload.sha256


def test_an_unreachable_server_keeps_the_record_in_the_cache_until_the_next_run(
    tmp_path, monkeypatch, caplog
):
    dsn, _ = _server_env(monkeypatch, tmp_path)  # tmp_path/server does not exist: the server is down
    failed = lambda: any("registry sync failed" in r.message for r in caplog.records)
    with (
        caplog.at_level(logging.WARNING, logger="qdt_server.runs"),
        TestClient(create_app(Settings(root=tmp_path / "registry", stream_port=0)), client=LOOPBACK) as c,
    ):
        reg = c.app.state.registry
        assert _until(failed)  # the start-up sync, against a server that is down
        caplog.clear()
        first = wait_for(c, c.post("/runs", json={"definition": definition()}).json()["run_id"])
        assert first.state == "completed" and first.record_id, first.error
        assert _until(failed)
        assert reg.unsynced()["records"] == 1  # kept, not lost; the run is unaffected
        assert all(DSN_ENV not in r.message and "server.sqlite" not in r.message for r in caplog.records)

        (tmp_path / "server").mkdir()  # the server comes up
        second = wait_for(c, c.post("/runs", json={"definition": definition()}).json()["run_id"])
        assert second.state == "completed" and second.record_id, second.error
        assert _until(lambda: reg.unsynced()["records"] == 0)  # both uploaded by one sync
    ids = {r.record_id for r in _records_on_the_server(tmp_path, dsn)}
    assert ids == {first.record_id, second.record_id}


def test_without_a_server_the_cache_is_the_registry(client, caplog):
    with caplog.at_level(logging.WARNING, logger="qdt_server.runs"):
        run = wait_for(client, client.post("/runs", json={"definition": definition()}).json()["run_id"])
        assert run.state == "completed", run.error
        time.sleep(0.2)
    assert client.app.state.registry.unsynced()["records"] == 1
    assert not [r for r in caplog.records if "sync" in r.message]  # nothing to try, nothing to warn


def test_a_server_uploads_what_an_earlier_session_left_when_it_starts(tmp_path, monkeypatch):
    root = tmp_path / "registry"
    with TestClient(create_app(Settings(root=root, stream_port=0)), client=LOOPBACK) as c:  # no server configured
        run = wait_for(c, c.post("/runs", json={"definition": definition()}).json()["run_id"])
        assert run.record_id, run.error
        assert c.app.state.registry.unsynced()["records"] == 1
    dsn, _ = _server_env(monkeypatch, tmp_path)
    (tmp_path / "server").mkdir()
    with TestClient(create_app(Settings(root=root, stream_port=0)), client=LOOPBACK) as c:  # the same cache, a server
        assert _until(lambda: c.app.state.registry.unsynced()["records"] == 0)
    assert [r.record_id for r in _records_on_the_server(tmp_path, dsn)] == [run.record_id]


# --- the read server (ADR 0074): no stand, no command; records, payloads and replay from the server ---


def _stand_server_that_measured_once(tmp_path, monkeypatch):
    """A stand server on the laptop that ran one sweep and synced it; (dsn, store, run)."""
    dsn, store = _server_env(monkeypatch, tmp_path)
    (tmp_path / "server").mkdir()
    with TestClient(create_app(Settings(root=tmp_path / "laptop", stream_port=0)), client=LOOPBACK) as c:
        run = wait_for(c, c.post("/runs", json={"definition": definition()}).json()["run_id"])
        assert run.state == "completed" and run.record_id, run.error
        assert _until(lambda: not any(c.app.state.registry.unsynced().values()))
    return dsn, store, run


STAND_ROUTES = [
    ("GET", "/stand"),
    ("GET", "/levels"),
    ("GET", "/levels/state"),
    ("POST", "/levels"),
    ("DELETE", "/levels"),
    ("GET", "/levels/pending"),
    ("POST", "/levels/pending/confirm"),
    ("DELETE", "/levels/pending"),
    ("GET", "/stand/state"),
    ("POST", "/stand/state"),
    ("POST", "/sweeps/compile"),
    ("POST", "/runs"),
    ("GET", "/runs"),
    ("POST", "/runs/x/abort"),
    ("POST", "/records/x/results"),
    ("GET", "/nodes"),
    ("POST", "/tuneups"),
    ("GET", "/tuneups"),
    ("POST", "/tuneups/x/stop"),
]


def test_a_read_server_serves_the_registry_and_has_no_command(tmp_path, monkeypatch):
    _, store, run = _stand_server_that_measured_once(tmp_path, monkeypatch)
    desktop = Settings(root=tmp_path / "desktop", stream_port=0, read_only=True)
    with TestClient(create_app(desktop), client=LOOPBACK) as c:
        assert c.get("/server").json() == {"read_only": True, "stand_id": None, "device_id": None}
        assert [d["device_id"] for d in c.get("/devices").json()] == [DEVICE_ID]
        [rec] = c.get("/records").json()
        assert rec["record_id"] == run.record_id
        assert c.get(f"/records/{run.record_id}").json()["record_id"] == run.record_id
        # the bytes, with their hash, as any application on the network would fetch them
        r = c.get(f"/records/{run.record_id}/payload")
        assert r.status_code == 200 and r.headers["content-type"] == "application/x-hdf5"
        got = hashlib.sha256(r.content).hexdigest()
        assert got == r.headers["x-content-sha256"] == rec["payload"]["sha256"]
        assert r.content == (store / rec["payload"]["path"]).read_bytes()
        assert c.get("/records/" + "0" * 32 + "/payload").status_code == 404
        assert c.get("/results").json() == [] and c.get("/outcomes").json() == []
        # the stand's state history, from the registry server (ADR 0075, 0085: the read server reads)
        [first] = c.get("/stand-states").json()
        assert (first["version"], first["set_by"]) == (1, "qdt-server")
        # replay works: the record goes on this server's own stream
        url = c.get("/stream").json()["url"]
        assert c.post("/stream/replay", json={"record_id": run.record_id}).status_code == 202
        assert asyncio.run(collect(url, timeout=30))
        # no command route exists — not refused, absent — and the API document says so
        for method, path in STAND_ROUTES:
            assert c.request(method, path, json={}).status_code in (404, 405), (method, path)
        paths = c.get("/openapi.json").json()["paths"]
        assert not any(p in paths for p in ("/stand", "/runs", "/levels", "/tuneups", "/nodes"))
        assert not hasattr(c.app.state, "runs")  # nothing that could sync or run
        assert c.app.state.registry.unsynced()["records"] == 0  # its own cache holds nothing


def test_a_read_server_needs_the_registry_server(tmp_path):
    desktop = Settings(root=tmp_path / "desktop", stream_port=0, read_only=True)
    with pytest.raises(RuntimeError, match=DSN_ENV), TestClient(create_app(desktop), client=LOOPBACK):
        pass


def test_a_stand_server_says_what_it_drives_and_serves_its_own_payloads(client):
    info = client.get("/server").json()
    assert info["read_only"] is False and info["device_id"] == DEVICE_ID and info["stand_id"]
    run = wait_for(client, client.post("/runs", json={"definition": definition()}).json()["run_id"])
    assert run.record_id, run.error
    r = client.get(f"/records/{run.record_id}/payload")
    assert r.status_code == 200
    assert hashlib.sha256(r.content).hexdigest() == r.headers["x-content-sha256"]
    for method, path in STAND_ROUTES:  # present here: a stand server has every route
        assert client.request(method, path, json={}).status_code not in (404, 405) or "/x/" in path
