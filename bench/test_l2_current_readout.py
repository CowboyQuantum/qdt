"""L2-2: current readout into a known load (`docs/BENCH.md` § L2; ADR 0016's load-dependent `LevelSense`).

A DC source drives the scope's 1 MΩ input and reads its own output current through `LevelSense`: the
oracle is I = V / R_scope, 1 µA per volt. Two rows, each on its own scope input (DC, 1 MΩ):

    QDAC ch02 → scope ch2  (`QDT_L2_QDAC_CHANNEL`, `QDT_L2_QDAC_SCOPE_CHANNEL`)
    SMU F/S   → scope ch3  (`QDT_L2_SMU_SCOPE_CHANNEL`)

The voltage in the oracle is the source's setpoint (the QDAC-II's 20-bit output and the 2450's
±(0.015 % + 300 µV) are far inside the scope's impedance tolerance); the scope's reading of the level
confirms the load is connected, within its datasheet accuracy (`scope_accuracy.py`). A line is fitted
through the (setpoint, current) points; its slope is 1/R_scope and its intercept the readout's offset.

Tolerances come from datasheets, no site figure (rule 7):
- the scope's input impedance, 1 MΩ ± `SCOPE_R_TOLERANCE` (HD3 datasheet: 1 MΩ ±1 %);
- the QDAC-II current readout in its LOW range (the HIGH range's common-mode error hides a 1 MΩ load,
  BENCH.md): the manual's accuracy is budgeted as `QDAC_I_GAIN` of reading + `QDAC_I_OFFSET_A`;
- the 2450's current measurement on its 10 µA range: `SMU_I_GAIN` of reading + `SMU_I_OFFSET_A`.
The QDAC's sense range is a front-panel setting the protocol leaves alone (how it is declared is a
pending decision, STATUS.md); this row switches it over the driver's transport, at 0 V, and back.
"""

import os
import time

import numpy as np
from scope_accuracy import ScopeChannel, dc_measurement_tolerance
from test_l1_loopback import read_dc

from qdt_schemas.stand import ChannelMap

SCOPE_R = 1e6
SCOPE_R_TOLERANCE = 0.01
"""HD3 datasheet: input impedance 1 MΩ ±1 %."""
QDAC_I_GAIN, QDAC_I_OFFSET_A = 0.01, 5e-9
"""QDAC-II current readout, LOW range: budgeted at 1 % of reading + 5 nA (manual; confirm)."""
SMU_I_GAIN, SMU_I_OFFSET_A = 0.001, 5e-9
"""Keithley 2450, 10 µA range: datasheet ±(0.025 % + 1.5 nA) at 1 NPLC, budgeted with margin."""
SETTLE_S = 0.3
INTEGRATION_S = 0.1
"""Readout aperture: 100 ms on both instruments (QDAC `sens:aper`, 2450 NPLC 6)."""
SMU_I_RANGE_A = 1e-5
"""The 2450's current measure range is held at 10 µA: left to autorange it drops to 10 nA at 0 V, and a
source behind a 10 nA measure range charges the cable at 10 nA, so the next level arrives late (bench,
2026-10-15: the scope still read the previous level 0.1 s after the set)."""

QDAC_LEVELS_V = (-1.0, -0.5, 0.0, 0.5, 1.0)
"""±1 µA: inside the QDAC-II's LOW current range."""
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


def test_qdac_current_readout_sees_the_scopes_megohm(qdac, scope, scope_front_panel):
    channel = os.environ.get("QDT_L2_QDAC_CHANNEL", "ch02")
    n = int(channel.removeprefix("ch"))
    sc = ScopeChannel(
        number=int(os.environ.get("QDT_L2_QDAC_SCOPE_CHANNEL", "2")), volts_per_div=0.5
    )
    scope_front_panel(sc.number, sc.volts_per_div, sc.offset_v, sc.coupling, sc.impedance)
    # the fixture builds the QDAC with no channel maps: declare the readout terminal and its aperture
    qdac._quantity[f"{channel}_i"] = "current"
    qdac._integration[f"{channel}_i"] = INTEGRATION_S
    t = qdac._t
    previous_range = t.query(f"sens{n}:rang?").strip()
    measured = {}
    try:
        qdac.set(channel, 0.0)
        time.sleep(SETTLE_S)
        t.write(f"sens{n}:rang low")
        for level in QDAC_LEVELS_V:
            qdac.set(channel, level)
            time.sleep(SETTLE_S)
            v_scope = read_dc(scope, f"ch{sc.number}")
            assert abs(v_scope - level) <= dc_measurement_tolerance(sc), (
                f"scope ch{sc.number} reads {v_scope:+.4f} V for {level:+.2f} V: is the QDAC on it?"
            )
            measured[level] = {"v": v_scope, "i": qdac.sense(f"{channel}_i")}
    finally:
        qdac.set(channel, 0.0)
        t.write(f"sens{n}:rang {previous_range}")
    check_row("QDAC", QDAC_LEVELS_V, measured, QDAC_I_GAIN, QDAC_I_OFFSET_A)


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
