"""L2-5: a DC level read by the sequencer's own input (`docs/BENCH.md` § L2-5; ADR 0067 on the bench).

Wiring: one QDAC channel → LF-FEM ai1 (`sensor`), one BNC; `QDT_L2_SENSOR_CHANNEL` names it by its logical
name (default `P2`, QDAC ch02; the other of `P1`/`P2` is the outer axis). The QDAC-II drives through its 50 Ω output
impedance into the FEM's 50 Ω input, so the level at the input is half the setpoint, the same halving
the L2-2 QDAC row saw at the scope's 50 Ω input. The input reads volts through Probe 02's constants
(`INTEGRATION_TO_VOLTS`, ADR 0044); its zero (−1.7 mV, Probe 02) is recorded, not applied.

A running `qdt-server --stand` owns the QDAC and the OPX (`QDT_SERVER_URL`, as `test_l2_capture.py`).
The rows post a DC map read in the shot (ADR 0067): a one-measure shot on the OPX at each point, the shots
averaged, over an outer axis on the other DAC channel (not cabled to the input) and an inner axis on the
cabled one. The compiler
paces the inner axis (ADR 0066): triggered through `dac_trigger` when the stand wires the DAC's trigger
input, else stepped from the host, one program run per point (ADR 0068); the second row forces the
host-stepped form so both are proven on the input.

Oracle: the plane fit over the (outer, inner) map has `slope_col` 1/2 (the divider), `slope_row` 0 (the
outer axis is not cabled to the input) and an offset that is the two zeros added: the DAC channel's and
the input's (Probe 02: −1.7 mV at 0 V in). The slope budget is the two 50 Ω impedances at 1 % each plus
Probe 02's 0.5 % agreement between its two constants: 3 % of 1/2. The offset budget is 10 mV: the input's
zero and a DAC zero of a few mV, as the L2-4 staircase read at the scope (−4 mV). No site tolerance is
written here (rule 7).
"""

import os

import pytest
from test_l2_capture import analyse, api, estimate, run_capture  # noqa: F401
from test_l2_paced import stand, stand_has  # noqa: F401

PLANNED_BY = ("ADR 0067", "ADR 0069")
"""The plan that asked for these rows (ADR 0071; `scripts/check_bench_rows.py`)."""

CABLED = os.environ.get("QDT_L2_SENSOR_CHANNEL", "P2")
"""The DAC channel on the FEM's input, by its logical name."""
OTHER = {"P1": "P2", "P2": "P1"}[CABLED]
OUTER = ("V_other", OTHER, -0.5, 0.5, 3)
INNER = ("V_in", CABLED, -0.8, 0.8, 9)
"""±0.8 V set is ±0.4 V at the 50 Ω input, inside the FEM's input range."""
MEASURE_NS = 10_000
SHOTS = 10
DIVIDER = 0.5
SLOPE_TOLERANCE = 0.03 * DIVIDER
INPUT_ZERO_V = -1.7e-3
"""The LF-FEM input's reading at 0 V in (Probe 02), which the driver does not apply."""
OFFSET_TOLERANCE_V = 10e-3
"""The input's zero plus the DAC channel's, a few mV (L2-4 read −4 mV at the scope)."""


def definition(name: str, stepping: str | None = None) -> dict:
    v1, p1, s1, e1, n1 = OUTER
    v2, p2, s2, e2, n2 = INNER
    inner = {"name": v2, "channel": p2, "start": s2, "stop": e2, "num": n2}
    if stepping:
        inner["stepping"] = stepping
    return {
        "name": name,
        "axes": [{"name": v1, "channel": p1, "start": s1, "stop": e1, "num": n1}, inner],
        "stage": {
            "instrument": "opx",
            "sequence": {
                "name": "read the input",
                "body": [
                    {
                        "op": "measure",
                        "channel": "sensor",
                        "duration": MEASURE_NS,
                        "result": "V_sensor",
                    }
                ],
            },
            "shots": SHOTS,
            "reduce": {"V_sensor": "mean"},
        },
    }


def pacing_of(api, definition: dict, axis: str) -> str:  # noqa: F811
    r = api.post("/sweeps/compile", json=definition)
    assert r.status_code == 200, r.text
    return next(p["pacing"] for p in r.json()["pacing"] if p["axis"] == axis)


def check_plane(api, record: dict) -> None:  # noqa: F811
    result = analyse(api, record, "qdt_analysis.plane.fit_plane")
    assert result["status"] == "ok", result["message"]
    col, row, offset = (estimate(result, n) for n in ("slope_col", "slope_row", "offset"))
    assert abs(col["value"] - DIVIDER) <= SLOPE_TOLERANCE, (
        f"{CABLED} slope {col['value']:.4f} ± {col['stderr']:.4f} V/V vs {DIVIDER} (50 Ω into 50 Ω)"
    )
    assert abs(row["value"]) <= SLOPE_TOLERANCE, (
        f"{OTHER} slope {row['value']:.4f} ± {row['stderr']:.4f} V/V vs 0 (not cabled to the input)"
    )
    assert abs(offset["value"]) <= OFFSET_TOLERANCE_V, (
        f"offset {offset['value'] * 1e3:+.2f} mV: the input's zero ({INPUT_ZERO_V * 1e3:+.1f} mV) plus the "
        "DAC's, within 10 mV"
    )
    assert estimate(result, "r2")["value"] > 0.999


@pytest.fixture(scope="module")
def sensor_input(stand):  # noqa: F811
    if not any(
        c["logical"] == "sensor" and c["instrument"] == "opx" and c["quantity"] == "voltage"
        for c in stand["channels"]
    ):
        pytest.skip("the stand needs the OPX's input as the voltage channel 'sensor'")
    if os.environ.get("QDT_L2_SENSOR") != "1":
        pytest.skip(
            "set QDT_L2_SENSOR=1 with a QDAC channel cabled to LF-FEM ai1 (QDT_L2_SENSOR_CHANNEL)"
        )


def test_l2_5_a_dc_level_read_in_the_shot_by_the_sequencers_input_is_halved(
    api,  # noqa: F811
    stand,  # noqa: F811
    sensor_input,
):
    """The map read in the shot, the inner axis paced as the stand allows: triggered when the DAC's
    trigger input is wired to the OPX (ADR 0064), else stepped from the host."""
    d = definition("l2-5 input read in the shot")
    wired = stand_has(stand, "dac0", "trigger_from", "trigger_in")
    assert pacing_of(api, d, "V_in") == ("triggered" if wired else "software")
    check_plane(api, run_capture(api, d))


def test_l2_5_stepped_from_the_host_the_input_is_read_once_per_point(
    api,  # noqa: F811
    stand,  # noqa: F811
    sensor_input,
):
    """ADR 0068 on the input: with the inner axis forced to software, every point is one program run
    whose one value lands at the stepped point."""
    d = definition("l2-5 input read once per point", stepping="software")
    assert pacing_of(api, d, "V_in") == "software"
    check_plane(api, run_capture(api, d))


def test_the_sequencers_input_is_not_sensed_per_point(api, stand):  # noqa: F811
    """Per point would need a LevelSense behind the input; the compiler refuses, naming the capability."""
    if not any(c["logical"] == "sensor" and c["instrument"] == "opx" for c in stand["channels"]):
        pytest.skip("the stand needs the OPX's input as channel 'sensor'")
    v1, p1, s1, e1, n1 = OUTER
    r = api.post(
        "/sweeps/compile",
        json={
            "name": "l2-5 sensed per point",
            "axes": [{"name": v1, "channel": p1, "start": s1, "stop": e1, "num": n1}],
            "sensed": [{"name": "V_sensor", "channel": "sensor"}],
        },
    )
    assert r.status_code == 400, r.text
    assert "lacks capability 'level_sense'" in r.text


def test_l2_5_the_triggered_staircase_captured_on_the_sequencers_input(
    api,  # noqa: F811
    stand,  # noqa: F811
    sensor_input,
):
    """ADR 0069 on the bench: L2-4's staircase with the OPX's own input as the scope. The DAC is
    advanced by the OPX's marker, the input records 20 µs per point in the shot, and the (V, time) map
    is a plane of slope 1/2 along V (the divider) and flat along time."""
    if not stand_has(stand, "dac0", "trigger_from", "trigger_in"):
        pytest.skip("the stand needs trigger_from (and trigger_in) on dac0")
    record = run_capture(
        api,
        {
            "name": "l2-5 staircase recorded on the input",
            "axes": [
                {
                    "name": "V",
                    "channel": CABLED,
                    "start": INNER[2],
                    "stop": INNER[3],
                    "num": 5,
                    "stepping": "triggered",
                }
            ],
            "stage": {
                "instrument": "opx",
                "sequence": {
                    "name": "record the input",
                    "body": [
                        {
                            "op": "capture",
                            "channel": "sensor",
                            "duration": 20_000,
                            "num": 200,
                            "result": "trace",
                        }
                    ],
                },
                "shots": 1,
            },
        },
    )
    result = analyse(api, record, "qdt_analysis.plane.fit_plane")
    assert result["status"] == "ok", result["message"]
    row, offset = estimate(result, "slope_row"), estimate(result, "offset")
    assert abs(row["value"] - DIVIDER) <= SLOPE_TOLERANCE, (
        f"V slope {row['value']:.4f} ± {row['stderr']:.4f} V/V vs {DIVIDER} (50 Ω into 50 Ω)"
    )
    assert abs(offset["value"]) <= OFFSET_TOLERANCE_V, f"offset {offset['value'] * 1e3:+.2f} mV"
    assert estimate(result, "r2")["value"] > 0.999, "a missed point leaves a row off the plane"
