"""L2-2: current readout into a known load (`docs/BENCH.md` § L2; ADR 0016's load-dependent `LevelSense`).

A DC source drives a scope input of known impedance and reads its own output current through
`LevelSense`: the oracle is I = V_scope / R_scope. Two rows, each on its own scope input:

    SMU F/S   → scope ch3 at 1 MΩ, 1 µA per volt          (`QDT_L2_SMU_SCOPE_CHANNEL`)
    QDAC ch03 → scope ch2 at 50 Ω, 1 mA per 0.1 V set     (`QDT_L2_QDAC_CHANNEL`, `QDT_L2_QDAC_SCOPE_CHANNEL`)

The QDAC row was specified at 1 MΩ with the LOW sense range; on the bench unit the LOW range returned
≈ 2 nA for any current and the HIGH range's zero (≈ +73 µA) hides 1 µA, so the row drives 1 mA into
the 50 Ω input where the HIGH range reads it (BENCH.md, QDAC-II quirks).

The voltage in the oracle is the source's setpoint (the QDAC-II's 20-bit output and the 2450's
±(0.015 % + 300 µV) are far inside the scope's impedance tolerance); the scope's reading of the level
confirms the load is connected, within its datasheet accuracy (`scope_accuracy.py`). A line is fitted
through the (setpoint, current) points; its slope is 1/R_scope and its intercept the readout's offset.

Tolerances come from datasheets, no site figure (rule 7):
- the scope's input impedance, 1 MΩ ± `SCOPE_R_TOLERANCE` (HD3 datasheet: 1 MΩ ±1 %);
- the scope's 50 Ω input ±1.5 % and the QDAC-II HIGH-range readout gain, budgeted as `QDAC_I_GAIN`; its
  zero is the line's intercept, checked against `QDAC_I_ZERO_A`;
- the 2450's current measurement on its 10 µA range: `SMU_I_GAIN` of reading + `SMU_I_OFFSET_A`.
The sense range is a front-panel setting the protocol leaves alone (how it is declared is a pending
decision, STATUS.md); the rows set it over the drivers' transports.
"""

import os
import time

import numpy as np
from scope_accuracy import ScopeChannel, dc_measurement_tolerance
from test_l1_loopback import read_dc

from qdt_schemas.stand import ChannelMap

PLANNED_BY = ("docs/steps/05-instrument-drivers-last-mile.md", "ADR 0040")
"""The plan that asked for these rows (ADR 0071; `scripts/check_bench_rows.py`)."""

SCOPE_R = 1e6
SCOPE_R_TOLERANCE = 0.01
"""HD3 datasheet: input impedance 1 MΩ ±1 %."""
SCOPE_R_FIFTY, SCOPE_R_FIFTY_TOLERANCE = 50.0, 0.015
"""HD3 datasheet: 50 Ω input ±1.5 %."""
QDAC_I_GAIN = 0.05
"""QDAC-II current readout, HIGH range, gain: budgeted at 5 % of reading (measured 2–3 % low; the manual's
figure to confirm)."""
QDAC_I_ZERO_A = 200e-6
"""The HIGH range's zero reading: ≈ +73 µA on this unit (the common-mode term BENCH.md describes)."""
SMU_I_GAIN, SMU_I_OFFSET_A = 0.001, 5e-9
"""Keithley 2450, 10 µA range: datasheet ±(0.025 % + 1.5 nA) at 1 NPLC, budgeted with margin."""
SETTLE_S = 0.3
INTEGRATION_S = 0.1
"""Readout aperture: 100 ms on both instruments (QDAC `sens:aper`, 2450 NPLC 6)."""
SMU_I_RANGE_A = 1e-5
"""The 2450's current measure range is held at 10 µA: left to autorange it drops to 10 nA at 0 V, and a
source behind a 10 nA measure range charges the cable at 10 nA, so the next level arrives late (bench,
2026-10-15: the scope still read the previous level 0.1 s after the set)."""

QDAC_LEVELS_V = (-0.1, -0.05, 0.0, 0.05, 0.1)
"""±1 mA at the sensor into 50 Ω (half the setpoint arrives: the QDAC's 50 Ω output impedance)."""
SMU_LEVELS_V = (-2.0, -1.0, 0.0, 1.0, 2.0)
"""±2 µA on the 2450's 10 µA range (1 mA compliance in the fixture is far away)."""


def line(v: np.ndarray, i: np.ndarray) -> tuple[float, float]:
    """(slope, intercept) of i against v by least squares."""
    slope, intercept = np.polyfit(v, i, 1)
    return float(slope), float(intercept)


def check_row(name: str, levels, measured: dict, i_gain: float, i_offset: float) -> None:
    v = np.array(levels)
    i = np.array([measured[x]["i"] for x in levels])
    slope, intercept = line(v, i)
    expected = 1 / SCOPE_R
    tol = expected * (SCOPE_R_TOLERANCE + i_gain)
    assert abs(slope - expected) <= tol, (
        f"{name}: {slope * 1e6:.4f} µA/V against {expected * 1e6:.4f} (1 MΩ), tolerance ±{tol * 1e6:.4f}"
    )
    assert abs(intercept) <= i_offset + i_gain * abs(i).max(), (
        f"{name}: intercept {intercept * 1e9:.2f} nA"
    )
    for x in levels:
        tol_i = i_gain * abs(x / SCOPE_R) + i_offset + abs(x / SCOPE_R) * SCOPE_R_TOLERANCE
        assert abs(measured[x]["i"] - x / SCOPE_R) <= tol_i, (
            f"{name} at {x:+.2f} V: {measured[x]['i'] * 1e9:+.1f} nA against {x / SCOPE_R * 1e9:+.1f} nA ±{tol_i * 1e9:.1f}"
        )


def test_qdac_current_readout_sees_the_scopes_fifty_ohms(qdac, scope, scope_front_panel):
    """The QDAC row drives the scope's 50 Ω input (±1 mA at ±0.1 V set) and reads in the HIGH range.
    The 1 MΩ load with the LOW range was tried first (BENCH.md): on this unit the LOW range returned
    ≈ 2 nA for 1 µA and for 1 mA alike, so it measures nothing, and the HIGH range's zero (≈ +73 µA)
    hides a 1 µA load; at 1 mA it is a constant the line's intercept absorbs. The QDAC's own 50 Ω output
    impedance halves the level at the scope, so the current is the scope's reading over 50 Ω."""
    channel = os.environ.get("QDT_L2_QDAC_CHANNEL", "ch03")
    n = int(channel.removeprefix("ch"))
    sc = ScopeChannel(
        number=int(os.environ.get("QDT_L2_QDAC_SCOPE_CHANNEL", "2")),
        volts_per_div=0.02,
        impedance="FIFTy",
    )
    scope_front_panel(sc.number, sc.volts_per_div, sc.offset_v, sc.coupling, sc.impedance)
    qdac._quantity[f"{channel}_i"] = "current"
    qdac._integration[f"{channel}_i"] = INTEGRATION_S
    t = qdac._t
    t.write(f"sens{n}:rang high")
    measured = {}
    try:
        for level in QDAC_LEVELS_V:
            qdac.set(channel, level)
            time.sleep(SETTLE_S)
            v_scope = read_dc(scope, f"ch{sc.number}")
            # the 50 Ω source into 50 Ω: half the setpoint arrives
            assert abs(v_scope - level / 2) <= dc_measurement_tolerance(sc), (
                f"scope ch{sc.number} reads {v_scope:+.4f} V for {level:+.3f} V set: is the QDAC on it, at 50 Ω?"
            )
            measured[level] = {"v": v_scope, "i": qdac.sense(f"{channel}_i")}
    finally:
        qdac.set(channel, 0.0)
        scope_front_panel(
            sc.number, 0.5, 0.0, "DC", "ONEMeg"
        )  # leave the input as the other rows expect
    v = np.array([measured[x]["v"] for x in QDAC_LEVELS_V])
    i = np.array([measured[x]["i"] for x in QDAC_LEVELS_V])
    slope, intercept = line(v, i)
    expected = 1 / SCOPE_R_FIFTY
    tol = expected * (SCOPE_R_FIFTY_TOLERANCE + QDAC_I_GAIN)
    assert abs(slope - expected) <= tol, (
        f"QDAC: {slope * 1e3:.3f} mA/V against {expected * 1e3:.3f} (50 Ω), tolerance ±{tol * 1e3:.3f}"
    )
    assert abs(intercept) <= QDAC_I_ZERO_A, (
        f"QDAC readout zero {intercept * 1e6:+.1f} µA (documented ≈ +73 µA)"
    )


def test_smu_current_readout_sees_the_scopes_megohm(smu, scope, scope_front_panel):
    sc = ScopeChannel(
        number=int(os.environ.get("QDT_L2_SMU_SCOPE_CHANNEL", "3")), volts_per_div=0.5
    )
    scope_front_panel(sc.number, sc.volts_per_div, sc.offset_v, sc.coupling, sc.impedance)
    # the fixture declares `out` (voltage); add the current readout on the same terminal with its aperture
    smu._channels["out_i"] = ChannelMap(
        logical="out_i",
        instrument="smu",
        channel="out_i",
        quantity="current",
        integration_s=INTEGRATION_S,
    )
    measured = {}
    smu._t.write(":SENS:CURR:RANG:AUTO OFF")
    smu._t.write(f":SENS:CURR:RANG {SMU_I_RANGE_A:g}")
    try:
        for level in SMU_LEVELS_V:
            smu.set("out", level)
            time.sleep(SETTLE_S)
            v_scope = read_dc(scope, f"ch{sc.number}")
            assert abs(v_scope - level) <= dc_measurement_tolerance(sc), (
                f"scope ch{sc.number} reads {v_scope:+.4f} V for {level:+.2f} V: is the SMU on it?"
            )
            measured[level] = {"v": v_scope, "i": smu.sense("out_i")}
    finally:
        smu.set("out", 0.0)
    check_row("SMU", SMU_LEVELS_V, measured, SMU_I_GAIN, SMU_I_OFFSET_A)
