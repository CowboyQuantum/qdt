"""L2 instrument-on-instrument through the control path (`docs/BENCH.md` § L2; ADR 0040, 0047).

The bench: QDAC ch01 → the combiner board's DC input, OPX LF-FEM ao1 → its pulse input, board out →
scope ch1 (DC, 1 MΩ). The scope is the sink (human decision, 2026-10-15). A running `qdt-server --stand`
owns the QDAC and the scope (`QDT_SERVER_URL`, default http://127.0.0.1:8700); this file talks to it
the way Flight Deck does: it posts capture sweeps, waits for the record, runs the curated fit on it
through the API, and asserts on the estimates. The OPX is *not* in the server's stand: this file plays
the pulse train itself through `WaveformSource.play` (`QDT_OPX_ADDRESS`; the rows that need it skip
without), because nothing in a sweep plays a waveform yet (ADR 0047). The scope's vertical settings and
trigger are applied over a second VISA session (`QDT_SCOPE_ADDRESS`), as the L1 rows do.

Oracles are Probe 03's measurements of the same board with the same scope (`docs/probes/03-combiner-
board.md`, fixtures in `bench/fixtures/probe03/`), and the scope's datasheet accuracy (see
`test_l1_loopback.py` for the formula). No site tolerance is written here (rule 7).

Rows:
- L2-1 (DC): the QDAC level stepped over ±1 V, one record per level; the plane fit's `slope_row` is the
  board's DC division into 1 MΩ (Probe 03: 2.589).
- L2-1 (DC + pulse): the same with the OPX pulse train playing and the record on the pulse plateau; the
  plane's `slope_row` is unchanged by the pulse and the plateau level follows the pulse amplitude with
  the pulse-side gain Probe 03 recorded.
- L2-3: a long OPX pulse into the pulse input, the edge and plateau captured; the single exponential's
  `tau` agrees with the same fit on Probe 03's record of the same step (`step_opx.npz`).
"""

import os
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from test_l1_loopback import ScopeChannel, dc_measurement_tolerance

PLANNED_BY = ("docs/steps/05-instrument-drivers-last-mile.md", "ADR 0040", "ADR 0047")
"""The plan that asked for these rows (ADR 0071; `scripts/check_bench_rows.py`)."""

FIXTURES = Path(__file__).parent / "fixtures" / "probe03"

# Probe 03, 2026-10-14, the same board into the same scope at 1 MΩ
DC_DIVISION_INTO_1M = 2.589
DC_OFFSET_V = -2.1e-3

# the OPX pulse train of Probe 03's `step_opx` section, replayed here
PULSE_V, PULSE_ON_S, PULSE_PERIOD_S, SAMPLE_RATE = 0.25, 30e-6, 60e-6, 1e9
OPX_SETTLE_S = 2.0
"""After `play`: the OPX reopens its machine and compiles; the scope must not capture before that."""

SCOPE = ScopeChannel(number=1, volts_per_div=0.2)
"""±0.8 V full scale: the DC levels (±0.39 V through the board) plus the pulse (≈ 0.2 V)."""
TRIGGER_LEVEL_V = 0.1
"""Rising-edge trigger for the full-amplitude pulse, AC-coupled so the DC level under it does not move it."""
OFFSET_TERM_V = 0.1 * SCOPE.volts_per_div + 1e-3
"""The scope's DC offset accuracy at this range (0.1 div + 1 mV): the error that does not cancel between
two plateau levels read at the same range."""

DC_LEVELS = (-1.0, 1.0, 9)
RECORD_AT_REST = {"start_s": 0.0, "stop_s": 1e-3, "num": 500}
RECORD_PLATEAU = {"start_s": 2e-6, "stop_s": 28e-6, "num": 1300}
"""Inside the 30 µs pulse: the plane fit wants a plane, not the edges."""
RECORD_STEP = {"start_s": -5e-6, "stop_s": 29e-6, "num": 3400}
"""The rising edge and the plateau, the falling edge left out: what the exponential fits."""


# --- the server ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api():
    """The running `qdt-server --stand` that owns the QDAC and the scope."""
    url = os.environ.get("QDT_SERVER_URL", "http://127.0.0.1:8700")
    client = httpx.Client(base_url=url, timeout=60)
    try:
        stand = client.get("/stand").json()
    except httpx.HTTPError:
        pytest.skip(f"no qdt-server at {url} (QDT_SERVER_URL)")
    caps = {i["id"]: i["capabilities"] for i in stand["instruments"]}
    if not any("waveform_sense" in c for c in caps.values()):
        pytest.skip("the server's stand has no WaveformSense instrument")
    yield client
    client.close()


def run_capture(api: httpx.Client, definition: dict, timeout_s: float = 300.0) -> dict:
    """Post `definition`, wait for its run, return the record. Fails on a failed or aborted run."""
    r = api.post("/runs", json={"definition": definition, "options": {"campaign": "l2"}})
    assert r.status_code == 202, r.text
    run = r.json()
    t0 = time.monotonic()
    while run["state"] in ("queued", "running"):
        assert time.monotonic() - t0 < timeout_s, f"run {run['run_id']} did not finish"
        time.sleep(0.5)
        run = api.get(f"/runs/{run['run_id']}").json()
    assert run["state"] == "completed", f"run {run['state']}: {run.get('error')}"
    return api.get(f"/records/{run['record_id']}").json()


def analyse(api: httpx.Client, record: dict, method: str, **parameters) -> dict:
    r = api.post(
        f"/records/{record['record_id']}/results", json={"method": method, "parameters": parameters}
    )
    assert r.status_code == 201, r.text
    result = r.json()
    api.post("/stream/replay", json={"record_id": record["record_id"]})  # the overlays, live
    return result


def estimate(result: dict, name: str) -> dict:
    return next(e for e in result["estimates"] if e["name"] == name)


def stepped(name: str, record: dict) -> dict:
    start, stop, num = DC_LEVELS
    return {
        "name": name,
        "axes": [{"name": "V_dc", "channel": "P1", "start": start, "stop": stop, "num": num}],
        "captured": [{"name": "trace", "channel": "scope1", **record}],
    }


def pulse_train(amplitude: float = PULSE_V) -> np.ndarray:
    n = round(PULSE_PERIOD_S * SAMPLE_RATE)
    w = np.zeros(n)
    w[: round(PULSE_ON_S * SAMPLE_RATE)] = amplitude
    return w


def slope_tolerance() -> float:
    """The DC division as a slope over ±1 V: the scope's gain accuracy at this range, twice (the probe's
    figure was taken with the same scope at the same setting, so this is generous)."""
    return 2 * 0.015 * (1 / DC_DIVISION_INTO_1M)


# --- L2-1, DC: the QDAC level stepped, the plane's row slope is the board's DC division ---------------


def test_l2_1_dc_levels_through_the_board_give_probe_03s_division(api, scope_front_panel):
    scope_front_panel(
        SCOPE.number, SCOPE.volts_per_div, SCOPE.offset_v, SCOPE.coupling, SCOPE.impedance
    )
    record = run_capture(api, stepped("l2-1 dc levels", RECORD_AT_REST))
    result = analyse(api, record, "qdt_analysis.plane.fit_plane")
    assert result["status"] == "ok", result["message"]
    slope = estimate(result, "slope_row")
    assert abs(slope["value"] - 1 / DC_DIVISION_INTO_1M) <= slope_tolerance(), (
        f"DC slope {slope['value']:.5f} ± {slope['stderr']:.5f} V/V vs 1/{DC_DIVISION_INTO_1M} = "
        f"{1 / DC_DIVISION_INTO_1M:.5f} (Probe 03), tolerance ±{slope_tolerance():.4f}"
    )
    offset = estimate(result, "offset")["value"]
    assert abs(offset - DC_OFFSET_V) <= dc_measurement_tolerance(SCOPE), f"offset {offset:+.4f} V"
    assert abs(estimate(result, "slope_col")["value"]) * RECORD_AT_REST["stop_s"] < 1e-3, (
        "a DC level drifts within a record"
    )
    assert estimate(result, "r2")["value"] > 0.999
    assert (
        len(result["annotations"]) == 8
    )  # the iso-lines Flight Deck draws on the (V_dc, time) map


# --- rows that need the OPX --------------------------------------------------------------------------


def test_l2_1_dc_plus_pulse_plateau_is_a_plane_in_dc_level_and_pulse_amplitude(
    request, api, scope_front_panel
):
    if not os.environ.get("QDT_OPX_ADDRESS"):
        pytest.skip("QDT_OPX_ADDRESS not set: the OPX plays the pulse train")
    opx = request.getfixturevalue("opx")
    offsets: dict[float, float] = {}
    try:
        for amplitude in (PULSE_V, PULSE_V / 2):
            # the trigger follows the pulse, at 40 % of its early height through the board (0.8 ×
            # amplitude), AC-coupled so the stepped DC level under it does not move the trigger point;
            # a level at the pulse's height triggered marginally and the AUTO sweep free-ran
            scope_front_panel(
                SCOPE.number,
                SCOPE.volts_per_div,
                SCOPE.offset_v,
                SCOPE.coupling,
                SCOPE.impedance,
                trigger_level_v=0.4 * 0.8 * amplitude,
                trigger_coupling="AC",
            )
            opx.play("ao1", pulse_train(amplitude), SAMPLE_RATE)
            time.sleep(OPX_SETTLE_S)
            record = run_capture(api, stepped(f"l2-1 dc + {amplitude:.3g} V pulse", RECORD_PLATEAU))
            result = analyse(api, record, "qdt_analysis.plane.fit_plane")
            assert result["status"] == "ok", result["message"]
            slope = estimate(result, "slope_row")["value"]
            assert abs(slope - 1 / DC_DIVISION_INTO_1M) <= slope_tolerance(), (
                f"with the pulse on, DC slope {slope:.5f} V/V vs {1 / DC_DIVISION_INTO_1M:.5f}"
            )
            offsets[amplitude] = estimate(result, "offset")["value"]
    finally:
        opx.stop("ao1")
    # the plateau level follows the pulse amplitude: the pulse-side gain over the plateau window, which
    # Probe 03's record of the same pulse gives directly (the side droops, so it is a window mean)
    gain = (offsets[PULSE_V] - offsets[PULSE_V / 2]) / (PULSE_V / 2)
    expected = probe_03_plateau_gain()
    # 10 % for the droop over the window, plus the scope's offset term on a difference of two levels
    # read at the same range (the gain term cancels between them)
    assert abs(gain - expected) <= 0.1 * expected + 2 * OFFSET_TERM_V / (PULSE_V / 2), (
        f"pulse-side gain over the plateau {gain:.3f} vs Probe 03's record {expected:.3f}"
    )


def probe_03_plateau_gain() -> float:
    d = np.load(FIXTURES / "step_opx.npz")
    t, y = d["t"], d["y"]
    window = (t >= RECORD_PLATEAU["start_s"]) & (t <= RECORD_PLATEAU["stop_s"])
    base = float(np.mean(y[(t < -1e-6) & (t > -10e-6)]))
    return float((np.mean(y[window]) - base) / PULSE_V)


def test_l2_3_the_boards_step_response_is_the_exponential_probe_03_recorded(
    request, api, scope_front_panel
):
    """The pulse side's handover from its capacitive to its resistive path: a droop with a time constant
    of a few µs (Probe 03). The oracle is the same fit on Probe 03's record of the same step."""
    if not os.environ.get("QDT_OPX_ADDRESS"):
        pytest.skip("QDT_OPX_ADDRESS not set: the OPX plays the step")
    from qdt_analysis.exponential import detect_edge, fit

    opx = request.getfixturevalue("opx")
    # ±0.4 V so the pulse's early plateau (≈ 0.8 × 0.25 V) does not clip; and a sweep leaves its last
    # level on the QDAC (ADR 0038 holds levels, never zeroes them), so the DC input is held at 0 here
    scope_front_panel(
        SCOPE.number,
        0.1,
        0.0,
        SCOPE.coupling,
        SCOPE.impedance,
        trigger_level_v=TRIGGER_LEVEL_V,
        trigger_coupling="AC",
    )
    try:
        opx.play("ao1", pulse_train(), SAMPLE_RATE)
        time.sleep(OPX_SETTLE_S)
        record = run_capture(
            api,
            {
                "name": "l2-3 step",
                "levels": [{"channel": "P1", "value": 0.0}],
                "captured": [{"name": "trace", "channel": "scope1", **RECORD_STEP}],
            },
        )
    finally:
        opx.stop("ao1")
    result = analyse(api, record, "qdt_analysis.exponential.fit_exponential")
    assert result["status"] == "ok", result["message"]
    tau = estimate(result, "tau")
    # the same estimator on Probe 03's record, over the same window after its edge
    d = np.load(FIXTURES / "step_opx.npz")
    t, y = d["t"], d["y"]
    edge = detect_edge(y)
    window = (np.arange(t.size) > edge) & (t <= RECORD_STEP["stop_s"])
    reference = fit(t[window], y[window])
    assert abs(tau["value"] - reference.tau) <= 0.3 * reference.tau, (
        f"tau {tau['value'] * 1e6:.2f} µs ± {tau['stderr'] * 1e6:.2f} vs {reference.tau * 1e6:.2f} µs on Probe 03's record"
    )
    assert estimate(result, "r2")["value"] > 0.9
    assert {a["kind"] for a in result["annotations"]} == {
        "marker"
    }  # the edge and τ, drawn on the trace
