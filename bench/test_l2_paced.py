"""L2 rows where the sequencer paces the measurement (`docs/BENCH.md` § L2; ADR 0063, 0064).

A running `qdt-server --stand` owns every instrument here: the QDAC, the scope *and the OPX* as the
stand's sequencer, with the OPX's marker lines wired as the stand file says (`scope_trigger` → the
scope's EXT TRIG IN, `dac_trigger` → the QDAC-II's trigger input; `docs/examples/example_stand/
bench.stand.example.json`). This file posts the definitions and asserts on the records, as
`test_l2_capture.py` does; rows skip when the server's stand lacks what they need.

Rows:
- L2-3 as one shot (ADR 0063): `step(P2_pulse, 0.25 V, 16 ns); capture(scope1, 29 µs)`, the scope
  triggering itself on the analog edge (AC, NORMal sweep) when its stand entry has no
  `trigger_from`, on the marker when it has; the exponential's τ against the same fit on Probe 03's
  record, as the per-point row.
- L2-4, the triggered staircase (ADR 0064): QDAC ch01 (`P1`) direct into scope ch1 at 1 MΩ, a
  triggered axis of five levels advanced by the OPX's marker into the QDAC's trigger input, a shot
  that captures the scope (its marker into EXT) and then waits 300 ms (the scope's re-arm, ADR 0063);
  the plane fit over the (V, time) map has a row slope of 1 V/V within the scope's gain accuracy
  and sees every row.
"""

import os
from pathlib import Path

import numpy as np
import pytest
from scope_accuracy import ScopeChannel, dc_measurement_tolerance
from test_l2_capture import RECORD_STEP, analyse, api, estimate, run_capture  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures" / "probe03"

STEP_V = 0.25
TRIGGER_LEVEL_V = 0.1
SHOT_WAIT_NS = 50_000_000
"""After the capture: with segmented acquisition the scope catches every trigger in hardware (Probe
05, 2026-10-16: 10/10 records down to 20 ms apart); the wait only keeps the shot's window and the
next point's settle apart. Through one `:SINGle` per record it would have to be 0.5 s (ADR 0065)."""
STAIRCASE = (-1.0, 1.0, 5)
STAIRCASE_SCOPE = ScopeChannel(
    number=int(os.environ.get("QDT_L2_STAIRCASE_SCOPE_CHANNEL", "1")), volts_per_div=0.5
)
"""The scope input QDAC ch01 is cabled to; its logical name in the stand is `scope<number>`."""
STAIRCASE_WINDOW = {"duration": 2_000_000, "num": 200}


def stand_has(stand: dict, instrument_id: str, *settings: str) -> bool:
    inst = next((i for i in stand["instruments"] if i["id"] == instrument_id), None)
    return inst is not None and all(k in inst.get("settings", {}) for k in settings)


@pytest.fixture(scope="module")
def stand(api):  # noqa: F811 - the fixture of test_l2_capture
    s = api.get("/stand").json()
    if not any("sequencer" in i["capabilities"] for i in s["instruments"]):
        pytest.skip(
            "the server's stand has no sequencer (the OPX must be in the stand for these rows)"
        )
    return s


def test_l2_3_as_one_shot_the_boards_step_response_is_the_exponential(
    api,  # noqa: F811
    stand,
    scope_front_panel,
):
    """The shot definition of L2-3: the stimulus is the step, the readout is the capture. Without a
    marker line the scope triggers itself on the analog edge and must wait for it (NORMal)."""
    from qdt_analysis.exponential import detect_edge, fit

    marker = stand_has(stand, "scope0", "trigger_from")
    scope_front_panel(
        1,
        0.1,
        0.0,
        "DC",
        "ONEMeg",
        trigger_level_v=None if marker else TRIGGER_LEVEL_V,
        trigger_coupling="AC",
        sweep="NORMal",
    )
    record = run_capture(
        api,
        {
            "name": "l2-3 one shot",
            "levels": [{"channel": "P1", "value": 0.0}],
            "stage": {
                "instrument": "opx",
                "sequence": {
                    "name": "step response",
                    "body": [
                        {"op": "step", "channel": "P2_pulse", "level": STEP_V, "duration": 16},
                        {
                            "op": "capture",
                            "channel": "scope1",
                            "duration": round(RECORD_STEP["stop_s"] * 1e9),
                            "num": RECORD_STEP["num"],
                            "result": "trace",
                        },
                        {"op": "wait", "duration": SHOT_WAIT_NS},
                    ],
                },
                "shots": 1,
            },
        },
    )
    result = analyse(api, record, "qdt_analysis.exponential.fit_exponential")
    assert result["status"] == "ok", result["message"]
    tau = estimate(result, "tau")
    d = np.load(FIXTURES / "step_opx.npz")
    t, y = d["t"], d["y"]
    edge = detect_edge(y)
    window = (np.arange(t.size) > edge) & (t <= RECORD_STEP["stop_s"])
    reference = fit(t[window], y[window])
    assert abs(tau["value"] - reference.tau) <= 0.3 * reference.tau, (
        f"tau {tau['value'] * 1e6:.2f} µs ± {tau['stderr'] * 1e6:.2f} vs {reference.tau * 1e6:.2f} µs on Probe 03's record"
    )
    assert estimate(result, "r2")["value"] > 0.9


def test_l2_4_a_triggered_staircase_on_the_qdac_is_captured_point_by_point(
    api,  # noqa: F811
    stand,
    scope_front_panel,
):
    """The QDAC is loaded once and advanced by the OPX; the scope records each point on the OPX's
    marker. Wiring: QDAC ch01 → scope ch1 (DC, 1 MΩ), no board."""
    if not (
        stand_has(stand, "dac0", "trigger_from", "trigger_in")
        and stand_has(stand, "scope0", "trigger_from")
    ):
        pytest.skip("the stand needs trigger_from on dac0 (and trigger_in) and on scope0")
    if os.environ.get("QDT_L2_STAIRCASE") != "1":
        pytest.skip(
            "set QDT_L2_STAIRCASE=1 with QDAC ch01 cabled directly to the scope input named by "
            "QDT_L2_STAIRCASE_SCOPE_CHANNEL (default 1), no board"
        )
    scope_front_panel(STAIRCASE_SCOPE.number, STAIRCASE_SCOPE.volts_per_div, 0.0, "DC", "ONEMeg")
    start, stop, num = STAIRCASE
    record = run_capture(
        api,
        {
            "name": "l2-4 triggered staircase",
            "axes": [
                {
                    "name": "V",
                    "channel": "P1",
                    "start": start,
                    "stop": stop,
                    "num": num,
                    "stepping": "triggered",
                }
            ],
            "stage": {
                "instrument": "opx",
                "sequence": {
                    "name": "staircase",
                    "body": [
                        {
                            "op": "capture",
                            "channel": f"scope{STAIRCASE_SCOPE.number}",
                            "result": "trace",
                            **STAIRCASE_WINDOW,
                        },
                        {"op": "wait", "duration": SHOT_WAIT_NS},
                    ],
                },
                "shots": 1,
            },
        },
    )
    # the (V, time) map is a plane whose row slope is the level arriving as is into 1 MΩ: 1 V/V within
    # the scope's gain accuracy, twice (as L2-1 budgets it); a missed trigger leaves a row empty and
    # the fit's r² falls
    result = analyse(api, record, "qdt_analysis.plane.fit_plane")
    assert result["status"] == "ok", result["message"]
    slope = estimate(result, "slope_row")
    assert abs(slope["value"] - 1.0) <= 2 * 0.015, (
        f"row slope {slope['value']:.4f} ± {slope['stderr']:.4f} V/V vs 1 (direct cable)"
    )
    offset = estimate(result, "offset")["value"]
    assert abs(offset) <= dc_measurement_tolerance(STAIRCASE_SCOPE), f"offset {offset:+.4f} V"
    assert estimate(result, "r2")["value"] > 0.999, "a missed point leaves a row off the plane"
