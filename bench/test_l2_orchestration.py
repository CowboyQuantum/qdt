"""L2 orchestration (Step 6c goal 2, rows T-1 … T-7; ADR 0075, 0084, 0085, 0086): every row is a queue
entry submitted to `qdt-server --stand` and run by the server; the scope is the sink. Oracles reuse the
proven rows of `docs/BENCH.md` and compute thresholds from datasheets (`scope_accuracy.py`), never site
tolerances (rule 7).

The file runs the stand server itself, so T-1 can restart it and confirm the held point it offers:

    QDT_STAND_FILE          the bench stand file (`*.stand.json`, gitignored; shape in
                            `docs/examples/example_stand/bench.stand.example.json`): the server runs
                            `--stand` on it
    QDT_L2_DEVICE_ID        the device the records are about (default `bench-loopback`)
    QDT_L2_SCOPE_CHANNEL    the scope input QDAC ch01 (`P1`) is cabled to, DC 1 MΩ, no board (default 1);
                            its logical name in the stand is `scope<n>`
    QDT_L2_ROWS             the rows cabled right now (default `T1,T2,T3,T4,T7`): T-5 needs the combiner
                            board on scope ch1 (L2-1's wiring), T-6 the two OPX lines on ch1 and ch3 at
                            50 Ω (L2-6's); a row not listed skips before anything is submitted
    QDT_L2_SERVER_ROOT      the spawned server's registry root (default a temporary directory); with
                            `QDT_REGISTRY_DSN` and `QDT_PAYLOAD_STORE` set the server syncs every record
                            to `qdt-db` (ADR 0080) and takes the stand's state from there at start (ADR 0085)
    QDT_L2_SIMULATED=1      run against the simulated stand instead (no instrument, no stand file): the
                            queue, the refusals, the restart and the records are checked; the oracles that
                            need the bench's wiring skip

Stop any other `qdt-server` on the measurement PC first: the spawned one opens the instruments.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from scope_accuracy import ScopeChannel, dc_measurement_tolerance

from qdt_schemas.payload_hdf5 import read_payload

PLANNED_BY = ("docs/steps/06c-lab-deployment.md",)
"""The plan that asked for these rows (ADR 0071; `scripts/check_bench_rows.py`)."""

REPO = Path(__file__).resolve().parents[1]
SIMULATED = os.environ.get("QDT_L2_SIMULATED") == "1"
ROWS = {
    r.strip().upper().replace("-", "")
    for r in os.environ.get("QDT_L2_ROWS", "T1,T2,T3,T4,T7").split(",")
    if r.strip()
}
SCOPE = ScopeChannel(number=int(os.environ.get("QDT_L2_SCOPE_CHANNEL", "1")), volts_per_div=0.5)
"""QDAC ch01 straight into this input at 1 MΩ: ±2 V full scale holds T-1's ±1.5 V."""
TOLERANCE_V = dc_measurement_tolerance(SCOPE)
LEVELS_V = (0.0, 0.5, -0.5, 1.5, -1.5)
"""T-1's levels, the L1 loopback row's (`docs/BENCH.md` § Loopback map)."""
HELD_AT_END_V = 0.5
"""Where T-1 leaves P1 held before the restart: distinct from 0, inside T-2's limit."""
T2_LIMIT = {"channel": "P1", "min_v": -1.0, "max_v": 1.0}
"""T-2's limit: P1 below 1.5 V, which T-1 reached."""
STAIRCASE = (-1.0, 1.0, 5)
"""T-3 and T-4: P1 from −1 to +1 V in five points (L2-4's)."""
WINDOW = {"duration": 2_000_000, "num": 200}
"""One capture per point: 2 ms, 200 samples (L2-4's window)."""
SHOT_WAIT_NS = 50_000_000
"""After a shot's capture: keeps the window and the next point's settle apart (L2-4, Probe 05)."""
ENTRY_TIMEOUT_S = 300.0
START_TIMEOUT_S = 120.0


def needs_row(row: str) -> None:
    if row.replace("-", "") not in ROWS:
        pytest.skip(
            f"{row} is not in QDT_L2_ROWS: cable it as docs/steps/06c-lab-deployment.md says and list it"
        )


def needs_bench(what: str) -> None:
    """An oracle that needs the bench's wiring: skipped against the simulated stand, which records a
    droop on its scope whatever P1 does."""
    if SIMULATED:
        pytest.skip(f"simulated stand: {what} needs the bench")


# --- the stand server, run by this file -----------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StandServer:
    """`python -m qdt_server` on this computer, on free ports, restartable on the same registry root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.port, self.stream_port = _free_port(), _free_port()
        self.args = [
            sys.executable,
            "-m",
            "qdt_server",
            "--root",
            str(root),
            "--port",
            str(self.port),
            "--stream-port",
            str(self.stream_port),
        ]
        if not SIMULATED:
            stand = os.environ.get("QDT_STAND_FILE")
            if not stand:
                pytest.skip(
                    "QDT_STAND_FILE not set (or QDT_L2_SIMULATED=1 for the simulated stand)"
                )
            self.args += [
                "--stand",
                stand,
                "--device-id",
                os.environ.get("QDT_L2_DEVICE_ID", "bench-loopback"),
            ]
        self.process: subprocess.Popen | None = None
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=60)

    def start(self) -> None:
        self.process = subprocess.Popen(
            self.args, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        t0 = time.monotonic()
        while time.monotonic() - t0 < START_TIMEOUT_S:
            if self.process.poll() is not None:
                err = (
                    self.process.stderr.read().decode(errors="replace")
                    if self.process.stderr
                    else ""
                )
                raise AssertionError(f"the stand server exited at start:\n{err[-2000:]}")
            try:
                if self.client.get("/server").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.25)
        raise AssertionError("the stand server did not answer")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None

    def restart(self) -> None:
        self.stop()
        self.start()


@pytest.fixture(scope="module")
def server():
    given = os.environ.get("QDT_L2_SERVER_ROOT")
    root = Path(given) if given else Path(tempfile.mkdtemp(prefix="qdt-l2-orchestration-"))
    s = StandServer(root)
    s.start()
    yield s
    s.stop()
    s.client.close()
    if not given:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def stand(server) -> dict:
    """What the rows need from the stand: P1, the scope input it is cabled to, the sequencer that
    paces a shot, and whether the scope is triggered by that sequencer's marker (`trigger_from`)."""
    s = server.client.get("/stand").json()
    channels = {c["logical"]: c for c in s["channels"]}
    scope = f"scope{SCOPE.number}"
    if "P1" not in channels or scope not in channels:
        pytest.skip(
            f"the stand has no P1 or no {scope}: set QDT_L2_SCOPE_CHANNEL to the input P1 is cabled to"
        )
    instruments = {i["id"]: i for i in s["instruments"]}
    scope_inst = instruments[channels[scope]["instrument"]]
    sequencer = next((i["id"] for i in s["instruments"] if "sequencer" in i["capabilities"]), None)
    return {
        "stand": s,
        "channels": channels,
        "scope": scope,
        "sequencer": sequencer,
        "triggered": "trigger_from" in scope_inst.get("settings", {}),
    }


@pytest.fixture(autouse=True)
def front_panel(request):
    """The scope's vertical settings for the cabled input (the driver leaves them to the row)."""
    if SIMULATED:
        return
    apply = request.getfixturevalue("scope_front_panel")
    apply(SCOPE.number, SCOPE.volts_per_div, SCOPE.offset_v, SCOPE.coupling, SCOPE.impedance)


# --- through the queue -----------------------------------------------------------------------------


def submit(c: httpx.Client, definition: dict) -> str:
    r = c.post(
        "/queue", json={"definition": definition, "options": {"campaign": "l2-orchestration"}}
    )
    assert r.status_code == 201, f"{definition['name']}: {r.status_code} {r.text}"
    return r.json()["queue_id"]


def entry(c: httpx.Client, queue_id: str) -> dict | None:
    return next((e for e in c.get("/queue").json()["entries"] if e["queue_id"] == queue_id), None)


def wait_finished(c: httpx.Client, queue_id: str, timeout_s: float = ENTRY_TIMEOUT_S) -> dict:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        e = entry(c, queue_id)
        assert e is not None, f"queue entry {queue_id} disappeared"
        if e["state"] not in ("queued", "running"):
            return e
        time.sleep(0.2)
    raise AssertionError(f"queue entry {queue_id} did not finish in {timeout_s:.0f} s")


def run_entry(c: httpx.Client, definition: dict) -> dict:
    """Submit `definition` as a queue entry, wait for it, return its record. The queue must be running."""
    e = wait_finished(c, submit(c, definition))
    assert e["state"] == "done", f"{definition['name']} {e['state']}: {e['message']}"
    return c.get(f"/records/{e['record_id']}").json()


def arrays(c: httpx.Client, record_id: str, workdir: Path) -> dict:
    """The record's payload over HTTP, as a reader on another computer gets it (ADR 0081)."""
    r = c.get(f"/records/{record_id}/payload")
    assert r.status_code == 200, r.text
    path = workdir / f"{record_id}.h5"
    path.write_bytes(r.content)
    return read_payload(path).arrays


def capture_op(scope: str) -> dict:
    return {"op": "capture", "channel": scope, "result": "trace", **WINDOW}


def reading(ctx: dict, name: str) -> dict:
    """One record of the scope input with nothing moved: a shot capture paced by the sequencer when the
    scope waits for its marker, else a capture the executor arms (the scope then triggers itself)."""
    if ctx["triggered"] or ctx["sequencer"] and not SIMULATED:
        return {
            "name": name,
            "stage": {
                "instrument": ctx["sequencer"],
                "sequence": {
                    "name": "read",
                    "body": [capture_op(ctx["scope"]), {"op": "wait", "duration": SHOT_WAIT_NS}],
                },
                "shots": 1,
            },
        }
    return {
        "name": name,
        "captured": [
            {"name": "trace", "channel": ctx["scope"], "start_s": 0.0, "stop_s": 1e-3, "num": 500}
        ],
    }


def read_scope(c: httpx.Client, ctx: dict, name: str, workdir: Path) -> float:
    record = run_entry(c, reading(ctx, name))
    return float(np.mean(arrays(c, record["record_id"], workdir)["trace"]))


def staircase(ctx: dict, name: str, stepping: str) -> dict:
    """P1 from −1 to +1 V in five points with one capture per point: L2-4's sweep, paced as asked."""
    start, stop, num = STAIRCASE
    axis = {
        "name": "V",
        "channel": "P1",
        "start": start,
        "stop": stop,
        "num": num,
        "stepping": stepping,
    }
    if ctx["sequencer"] is None:
        return {
            "name": name,
            "axes": [axis],
            "captured": [
                {
                    "name": "trace",
                    "channel": ctx["scope"],
                    "start_s": 0.0,
                    "stop_s": 2e-3,
                    "num": 200,
                }
            ],
        }
    return {
        "name": name,
        "axes": [axis],
        "stage": {
            "instrument": ctx["sequencer"],
            "sequence": {
                "name": "staircase",
                "body": [capture_op(ctx["scope"]), {"op": "wait", "duration": SHOT_WAIT_NS}],
            },
            "shots": 1,
        },
    }


def analyse(c: httpx.Client, record: dict, method: str) -> dict:
    r = c.post(f"/records/{record['record_id']}/results", json={"method": method, "parameters": {}})
    assert r.status_code == 201, r.text
    return r.json()


def estimate(result: dict, name: str) -> float:
    return next(e["value"] for e in result["estimates"] if e["name"] == name)


def assert_staircase_oracle(c: httpx.Client, record: dict) -> None:
    """L2-4's oracle: the plane fit over the (V, time) map has row slope 1 V/V within the scope's gain
    accuracy twice, an offset within the DC tolerance, and every row on the plane (r²)."""
    result = analyse(c, record, "qdt_analysis.plane.fit_plane")
    assert result["status"] == "ok", result["message"]
    needs_bench("the staircase's plane")
    slope = estimate(result, "slope_row")
    assert abs(slope - 1.0) <= 2 * 0.015, f"row slope {slope:.4f} V/V vs 1 (direct cable)"
    offset = estimate(result, "offset")
    assert abs(offset) <= TOLERANCE_V, f"offset {offset:+.4f} V (±{TOLERANCE_V:.3f})"
    assert estimate(result, "r2") > 0.999, "a missed point leaves a row off the plane"


@pytest.fixture
def running(server):
    """The queue running when a row starts (a restart may have left it paused, ADR 0086)."""
    server.client.post("/queue/resume")
    return server.client


# --- T-1: hold a level, restart, confirm ------------------------------------------------------------


def test_t1_hold_a_level_and_get_it_back_after_a_restart(server, stand, running, tmp_path):
    """QDAC ch01 held at 0, ±0.5, ±1.5 V, the scope's mean against the setpoint (the L1 loopback's
    oracle). Then the stand server restarts: the held point is offered, not applied; confirmed, it is
    held again and the scope reads it."""
    needs_row("T-1")
    c = running
    for v in LEVELS_V:
        r = c.post("/levels", json=[{"channel": "P1", "value": v}])
        assert r.status_code == 200, f"P1 = {v} V: {r.text}"
        mean = read_scope(c, stand, f"t-1 at {v:+.1f} V", tmp_path)
        if not SIMULATED:
            assert abs(mean - v) <= TOLERANCE_V, (
                f"scope read {mean:+.4f} V with P1 held at {v:+.1f} V (±{TOLERANCE_V:.3f})"
            )
    assert c.post("/levels", json=[{"channel": "P1", "value": HELD_AT_END_V}]).status_code == 200
    version = c.get("/stand/state").json()["version"]

    server.restart()
    c = server.client
    assert c.get("/levels").json() == [], (
        "a restart must not re-apply the held point unasked (ADR 0075)"
    )
    pending = {lv["channel"]: lv["value"] for lv in c.get("/levels/pending").json()}
    assert pending.get("P1") == HELD_AT_END_V, f"offered after the restart: {pending}"
    assert c.get("/stand/state").json()["version"] == version, "the stand state came back as it was"
    r = c.post("/levels/pending/confirm")
    assert r.status_code == 200, r.text
    assert {lv["channel"]: lv["value"] for lv in r.json()}.get("P1") == HELD_AT_END_V
    c.post("/queue/resume")
    mean = read_scope(c, stand, "t-1 after the restart", tmp_path)
    if not SIMULATED:
        assert abs(mean - HELD_AT_END_V) <= TOLERANCE_V, (
            f"after confirming, the scope read {mean:+.4f} V (±{TOLERANCE_V:.3f})"
        )


# --- T-2: limits refuse -----------------------------------------------------------------------------


def test_t2_a_level_and_a_sweep_beyond_a_limit_are_refused_and_nothing_moves(
    running, stand, tmp_path
):
    """With P1 limited below 1.5 V, a level and a compiled sweep that reach it are refused (at the
    level, at compile and at the queue); the scope's mean is unchanged from before the refusals."""
    needs_row("T-2")
    c = running
    before = read_scope(c, stand, "t-2 before", tmp_path)
    previous = c.get("/stand/state").json()["limits"]
    limits = [lim for lim in previous if lim["channel"] != "P1"] + [T2_LIMIT]
    r = c.post("/stand/state", json={"limits": limits, "reason": "T-2: P1 limited below 1.5 V"})
    assert r.status_code == 201, r.text
    try:
        level = c.post("/levels", json=[{"channel": "P1", "value": 1.5}])
        assert level.status_code == 400 and "beyond its limit" in level.json()["detail"], level.text
        beyond = staircase(stand, "t-2 beyond the limit", "software")
        beyond["axes"][0].update(start=0.0, stop=1.5)
        compiled = c.post("/sweeps/compile", json=beyond)
        assert (
            compiled.status_code == 400 and "P1 would reach 0 to 1.5" in compiled.json()["detail"]
        ), compiled.text
        queued = c.post("/queue", json={"definition": beyond})
        assert queued.status_code == 400, queued.text
        after = read_scope(c, stand, "t-2 after", tmp_path)
    finally:
        restored = c.post(
            "/stand/state", json={"limits": previous, "reason": "T-2 done: limits as before"}
        )
        assert restored.status_code == 201, restored.text
    if not SIMULATED:
        assert abs(after - before) <= TOLERANCE_V, (
            f"the scope read {before:+.4f} V before and {after:+.4f} V after"
        )


# --- T-3, T-4: staircases ---------------------------------------------------------------------------


def test_t3_host_stepped_staircase(running, stand):
    """P1 −1 … +1 V in 5 points, set from the host, one capture per point; L2-4's oracle."""
    needs_row("T-3")
    record = run_entry(running, staircase(stand, "t-3 host-stepped staircase", "software"))
    assert record["outcome"] == "completed"
    assert_staircase_oracle(running, record)


def test_t4_triggered_staircase(running, stand):
    """L2-4 as a queue entry: the sequencer advances P1 through its loaded list (ADR 0064)."""
    needs_row("T-4")
    definition = staircase(stand, "t-4 triggered staircase", "triggered")
    compiled = running.post("/sweeps/compile", json=definition)
    if compiled.status_code == 400:
        pytest.skip(f"the stand cannot trigger P1's list: {compiled.json()['detail']}")
    plan = compiled.json()
    assert {p["axis"]: p["pacing"] for p in plan["pacing"]}["V"] == "triggered"
    record = run_entry(running, definition)
    assert_staircase_oracle(running, record)


# --- T-5: DC + pulse (L2-1) -------------------------------------------------------------------------


def test_t5_dc_levels_through_the_board(running, stand):
    """L2-1's capture sweep as a queue entry, QDAC ch01 through the combiner board onto scope ch1: the
    plane's row slope is the board's DC division into 1 MΩ (Probe 03), as `test_l2_capture.py` checks
    it. The pulse half of L2-1 plays the OPX beside the sweep, which only a stand without the OPX allows;
    it stays in `test_l2_capture.py` until #147 decides how the row covers it."""
    needs_row("T-5")
    from test_l2_capture import DC_DIVISION_INTO_1M, DC_LEVELS, slope_tolerance

    start, stop, num = DC_LEVELS
    definition = staircase(stand, "t-5 dc levels through the board", "software")
    definition["axes"][0].update(name="V_dc", start=start, stop=stop, num=num)
    record = run_entry(running, definition)
    result = analyse(running, record, "qdt_analysis.plane.fit_plane")
    assert result["status"] == "ok", result["message"]
    needs_bench("the board's division")
    slope = estimate(result, "slope_row")
    assert abs(slope - 1 / DC_DIVISION_INTO_1M) <= slope_tolerance(), (
        f"DC slope {slope:.5f} V/V vs 1/{DC_DIVISION_INTO_1M} (Probe 03), tolerance ±{slope_tolerance():.4f}"
    )


# --- T-6: two lines in one shot (L2-6) --------------------------------------------------------------


def two_lines() -> dict:
    from test_l2_two_lines import (
        FIRST_NS,
        LEVEL_V,
        ON_CH1,
        ON_CH3,
        POINTS,
        SHOTS,
        WINDOW_NS,
    )
    from test_l2_two_lines import (
        SHOT_WAIT_NS as WAIT,
    )

    return {
        "name": "t-6 two lines",
        "stage": {
            "instrument": "opx",
            "sequence": {
                "name": "two lines",
                "body": [
                    {"op": "step", "channel": ON_CH1, "level": LEVEL_V, "duration": FIRST_NS},
                    {"op": "step", "channel": ON_CH3, "level": LEVEL_V, "duration": 16},
                    {
                        "op": "capture",
                        "channel": "scope1",
                        "duration": WINDOW_NS,
                        "num": POINTS,
                        "result": "ch1",
                    },
                    {
                        "op": "capture",
                        "channel": "scope3",
                        "duration": WINDOW_NS,
                        "num": POINTS,
                        "result": "ch3",
                    },
                    {"op": "wait", "duration": WAIT},
                ],
            },
            "shots": SHOTS,
        },
    }


def test_t6_two_lines_in_one_shot(running, stand, tmp_path, request):
    """L2-6 as a queue entry: both plateaus at 0.25 V, ch3's edge 1000 ns after ch1's on every shot.
    The scope must trigger itself on ch1's edge (no `trigger_from` on it in the stand file)."""
    needs_row("T-6")
    needs_bench("L2-6's wiring")
    if stand["triggered"]:
        pytest.skip(
            "the scope waits for the sequencer's marker: take trigger_from off it for T-6 (L2-6)"
        )
    from test_l2_two_lines import (
        FIRST_NS,
        LEVEL_V,
        ON_CH1,
        ON_CH3,
        PLATEAU_TOLERANCE_V,
        POINTS,
        SKEW_TOLERANCE_NS,
        TRIGGER_LEVEL_V,
        VOLTS_PER_DIV,
        WINDOW_NS,
        crossing_ns,
    )

    apply = request.getfixturevalue("scope_front_panel")
    apply(1, VOLTS_PER_DIV, 0.0, "DC", "FIFTy", trigger_level_v=TRIGGER_LEVEL_V, sweep="NORMal")
    apply(3, VOLTS_PER_DIV, 0.0, "DC", "FIFTy")
    try:
        record = run_entry(running, two_lines())
    finally:  # T-7 and the reruns read P1 at 1 MΩ on the L1 input again
        apply(SCOPE.number, SCOPE.volts_per_div, SCOPE.offset_v, SCOPE.coupling, SCOPE.impedance)
    data = arrays(running, record["record_id"], tmp_path)
    ch1, ch3 = np.atleast_2d(data["ch1"]), np.atleast_2d(data["ch3"])
    t_ns = np.linspace(0.0, WINDOW_NS, POINTS)
    assert np.all(ch3[:, 0] < LEVEL_V / 2), (
        f"ch3 is already high at t = 0: {ON_CH1} and {ON_CH3} are swapped (QDT_L2_LINE_ON_CH1)"
    )
    late = t_ns > FIRST_NS + 1000
    for name, trace in (("ch1", ch1), ("ch3", ch3)):
        plateau = trace[:, late].mean(axis=1)
        assert np.all(np.abs(plateau - LEVEL_V) <= PLATEAU_TOLERANCE_V), (
            f"{name} plateau {plateau} V"
        )
    skews = np.array(
        [
            crossing_ns(t_ns, ch3[k], LEVEL_V / 2) - crossing_ns(t_ns, ch1[k], LEVEL_V / 2)
            for k in range(ch1.shape[0])
        ]
    )
    assert np.all(np.abs(skews - FIRST_NS) <= SKEW_TOLERANCE_NS), (
        f"skew {skews} ns vs {FIRST_NS} ns"
    )


# --- T-7: the queue as a whole ----------------------------------------------------------------------


def test_t7_the_queue_as_a_whole(running, stand, tmp_path):
    """T-3 … T-6 submitted together; one entry moved and one removed before it starts; one aborted
    while running. Oracle: the records reach the registry in the final queue order; the aborted entry
    ends aborted with no record; the removed entry never runs; afterwards the held point is still the
    server's, and the scope reads the level the stand reports for P1. (The step file says the scope
    reads the held point; a sweep leaves its last level and the held point is not re-applied, #147.)"""
    needs_row("T-7")
    c = running
    held_before = c.get("/levels").json()
    c.post("/queue/pause")
    candidates = [
        staircase(stand, "t-7 host-stepped staircase", "software"),
        staircase(stand, "t-7 triggered staircase", "triggered"),
        staircase(stand, "t-7 dc levels", "software"),
        two_lines(),
        reading(stand, "t-7 reading"),
    ]
    candidates[2]["axes"] = [dict(candidates[2]["axes"][0], name="V_dc", num=9)]
    ids: dict[str, str] = {}
    refused: dict[str, str] = {}
    try:
        for d in candidates:
            r = c.post(
                "/queue", json={"definition": d, "options": {"campaign": "l2-orchestration"}}
            )
            if r.status_code == 201:
                ids[d["name"]] = r.json()["queue_id"]
            else:
                refused[d["name"]] = r.json()["detail"]
        assert len(ids) >= 4, f"T-7 needs four entries the stand accepts; refused: {refused}"
        order = list(ids)
        # move the last to the front, remove the third of the new order
        last = order.pop()
        assert c.post(f"/queue/{ids[last]}/move", json={"position": 0}).status_code == 200
        order.insert(0, last)
        removed = order.pop(2)
        assert c.delete(f"/queue/{ids[removed]}").status_code == 200
        waiting = [
            e["request"]["definition"]["name"]
            for e in c.get("/queue").json()["entries"]
            if e["state"] == "queued"
        ]
        assert waiting == order, f"the server's order {waiting} vs {order}"
    finally:
        c.post("/queue/resume")
    # abort the second entry of the final order as soon as it runs
    target = order[1]
    t0 = time.monotonic()
    while (e := entry(c, ids[target]))["state"] == "queued":
        assert time.monotonic() - t0 < ENTRY_TIMEOUT_S, f"{target} never started"
        time.sleep(0.05)
    if e["state"] == "running":
        assert c.post(f"/queue/{ids[target]}/abort").status_code == 200
    finished = {name: wait_finished(c, ids[name]) for name in order}
    aborted = finished[target]
    assert aborted["state"] == "aborted", f"{target} ended {aborted['state']}: {aborted['message']}"
    if SIMULATED:  # the simulated stand streams at once, so an abort may land after the first frame
        assert (
            aborted["record_id"] is None
            or c.get(f"/records/{aborted['record_id']}").json()["outcome"] == "aborted"
        )
    else:
        assert aborted["record_id"] is None, (
            f"{target} recorded {aborted['record_id']} before the abort landed: it streamed first (abort earlier)"
        )
    done = [n for n in order if n != target]
    for n in done:
        assert finished[n]["state"] == "done", (
            f"{n} ended {finished[n]['state']}: {finished[n]['message']}"
        )
    by_time = sorted(done, key=lambda n: finished[n]["finished_at"])
    assert by_time == done, f"ran in {by_time}, queued as {done}"
    records = [c.get(f"/records/{finished[n]['record_id']}").json() for n in done]
    assert [r["definition_name"] for r in records] == done
    assert [r["started_at"] for r in records] == sorted(r["started_at"] for r in records)
    assert all(
        e["request"]["definition"]["name"] != removed for e in c.get("/queue").json()["entries"]
    )
    assert removed not in [r["definition_name"] for r in c.get("/records").json()], f"{removed} ran"
    # afterwards: the held point is still held, and the scope agrees with what the stand reports for P1
    # (a sweep leaves its last level on the stand, ADR 0038; the held point is not re-applied after it)
    assert c.get("/levels").json() == held_before
    p1 = next(r for r in c.get("/levels/state").json() if r["channel"] == "P1")
    mean = read_scope(c, stand, "t-7 afterwards", tmp_path)
    if not SIMULATED:
        assert abs(mean - p1["setpoint"]) <= TOLERANCE_V, (
            f"scope {mean:+.4f} V vs P1's setpoint {p1['setpoint']:+.4f} V"
        )
