"""Probe 03 — the combiner board (docs/probes/03-combiner-board.md).

Wiring: QDAC ch01 → board DC side; OPX LF-FEM ao1 → board pulse side; board out → scope ch1 (1 MΩ, DC).
The board's output impedance is tens of kΩ, so its sink must be high-impedance (the scope), not the
OPX's 50 Ω input; `--meter-mv` is a hand meter's reading of the output at 1 V on the QDAC side, from
which the output impedance follows (the meter is 10 MΩ, the scope 1 MΩ).

Sections, each landing in --out as JSON (and raw records as .npz):
  dc_qdac        QDAC levels ±1 V → scope mean; slope = DC-side division into 1 MΩ
  step_qdac      a 0 → 1 V QDAC step → the DC side's time constant and bandwidth
  step_opx       a long OPX pulse (0.25 V) → plateau (pulse-side division), 10–90 % rise, exponential τ
  superposition  QDAC 0.5 V with the OPX pulse: the two contributions add
  sines_opx      OPX sines 20 kHz–5 MHz at 0.2 V → amplitude vs frequency, −3 dB point
  sines_qdac     QDAC sine generator 20 Hz–20 kHz at 1 Vpp → amplitude vs frequency, −3 dB point

Usage: python combiner_probe.py --qdac ASRL... --opx <host> --scope TCPIP::...::5025::SOCKET [--meter-mv 396]
Amplitudes stay small: ≤ 1 V on the QDAC side, ≤ 0.25 V on the OPX side (the board's output stays
under 0.5 V). Everything through the drivers except the scope's front-panel settings and the QDAC's
waveform generator, which the protocols do not cover.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from qdt_lab.stream import assemble
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.stand import ChannelMap, InstrumentConfig

QDAC_LEVELS_V = (-1.0, -0.5, 0.0, 0.5, 1.0)
QDAC_NOMINAL_DIVISION = 2.5
OPX_NOMINAL_DIVISION = 1.8
OPX_PULSE_V, OPX_PULSE_ON_S, OPX_PULSE_PERIOD_S = 0.25, 30e-6, 60e-6
OPX_SINE_V = 0.2
OPX_SINE_HZ = (20e3, 50e3, 100e3, 200e3, 500e3, 1e6, 2e6, 5e6)
QDAC_SINE_VPP = 1.0
QDAC_SINE_HZ = (20.0, 100.0, 500.0, 1e3, 2e3, 5e3, 10e3, 20e3)
SAMPLE_RATE = 1e9
SETTLE_S = 0.3
OPX_SETTLE_S = 2.0
"""After `play`: the OPX reopens its machine for each new waveform and compiles; 0.3 s was too short and
the scope captured the output stuck at the previous level."""


def record(start: float, stop: float, num: int) -> Dataset:
    return Dataset(
        dataset_id="probe03",
        name="probe03",
        dims=(Dimension(name="record", size=1), Dimension(name="t", size=num)),
        coords=(LinearCoordinate(name="time", dim="t", unit="s", start=start, stop=stop, num=num),),
        data_vars=(DataVariable(name="voltage", dims=("record", "t"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="live"),
        created_at=datetime.now(UTC),
    )


def capture(scope, start: float, stop: float, num: int) -> tuple[np.ndarray, np.ndarray]:
    ds = record(start, stop, num)
    out = assemble(ds, scope.arm("ch1", ds, "voltage").frames())
    return out["time"].values, out["voltage"].values[0]


class Bench:
    def __init__(self, a):
        from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX
        from qdt_lab.drivers.qdevil.qdac2 import QDac2
        from qdt_lab.drivers.qm.opx1000 import Opx1000

        self.qdac = QDac2.from_config(
            InstrumentConfig(
                id="dac0",
                backend="qdac2",
                capabilities=("level_source",),
                settings={"address": a.qdac},
            ),
            (),
        )
        self.opx = Opx1000.from_config(
            InstrumentConfig(
                id="opx",
                backend="qua",
                capabilities=("waveform_source",),
                settings={"address": a.opx, "fem": a.fem, "output_mode": "direct"},
            ),
            (),
        )
        self.scope = InfiniiVisionX.from_config(
            InstrumentConfig(
                id="scope0",
                backend="infiniivision",
                capabilities=("waveform_sense",),
                settings={"address": a.scope},
            ),
            (ChannelMap(logical="ch1", instrument="scope0", channel="1", quantity="voltage"),),
        )
        self._scpi = self.scope._t  # front-panel settings the protocol leaves to the user
        self._q = self.qdac._t  # the QDAC's waveform generator, not in the protocols

    def front_panel(self, volts_per_div: float, trigger_level_v: float | None = None) -> None:
        w = self._scpi.write
        w(":CHANnel1:DISPlay 1")
        w(":CHANnel1:COUPling DC")
        w(":CHANnel1:IMPedance ONEMeg")
        w(":CHANnel1:PROBe 1")
        w(f":CHANnel1:SCALe {volts_per_div:.6g}")
        w(":CHANnel1:OFFSet 0")
        w(":TRIGger:SWEep AUTO")
        w(":TRIGger:MODE EDGE")
        w(":TRIGger:EDGE:SOURce CHANnel1")
        w(":TRIGger:EDGE:SLOPe POSitive")
        w(f":TRIGger:EDGE:LEVel {trigger_level_v if trigger_level_v is not None else 0.0:.6g}")

    def qdac_sine(self, hz: float, vpp: float) -> None:
        q = self._q.write
        q("sour1:sine:abor")
        q(f"sour1:sine:freq {hz:.6g}")
        q(f"sour1:sine:span {vpp:.6g}")
        q("sour1:sine:count inf")
        q("sour1:sine:trig:sour imm")
        q("sour1:sine:init")

    def qdac_sine_stop(self) -> None:
        self._q.write("sour1:sine:abor")
        self.qdac.set("ch01", 0.0)

    def close(self) -> None:
        try:
            self.opx.stop("ao1")
            self.qdac_sine_stop()
        finally:
            self.scope.close()
            self.opx.close()
            self.qdac.close()


def dc_qdac(b: Bench) -> dict:
    b.front_panel(0.2)
    b.opx.stop("ao1")
    levels, means = [], []
    for v in QDAC_LEVELS_V:
        b.qdac.set("ch01", v)
        time.sleep(SETTLE_S)
        _, y = capture(b.scope, 0.0, 1e-3, 1000)
        levels.append(v)
        means.append(float(np.mean(y)))
    b.qdac.set("ch01", 0.0)
    slope, off = np.polyfit(levels, means, 1)
    resid = np.array(means) - (slope * np.array(levels) + off)
    return {
        "levels_v": levels,
        "scope_mean_v": means,
        "gain_into_1M": float(slope),
        "division_into_1M": float(1 / slope),
        "offset_mv": float(off * 1e3),
        "max_residual_mv": float(np.abs(resid).max() * 1e3),
        "nominal_division": QDAC_NOMINAL_DIVISION,
    }


def pulse_train(on_s: float, period_s: float, amplitude: float) -> np.ndarray:
    n = round(period_s * SAMPLE_RATE)
    w = np.zeros(n)
    w[: round(on_s * SAMPLE_RATE)] = amplitude
    return w


def edge_metrics(t: np.ndarray, y: np.ndarray, on_s: float) -> dict:
    base = float(np.mean(y[(t < -0.1 * on_s) & (t > -0.5 * on_s)]))
    plateau = float(np.mean(y[(t > 0.8 * on_s) & (t < on_s)]))
    amp = plateau - base
    lo, hi = base + 0.1 * amp, base + 0.9 * amp
    rising = (t >= 0) & (t <= on_s)
    tr, yr = t[rising], y[rising]
    i10 = int(np.argmax(yr >= lo)) if amp > 0 else int(np.argmax(yr <= lo))
    i90 = int(np.argmax(yr >= hi)) if amp > 0 else int(np.argmax(yr <= hi))
    rise = float(tr[i90] - tr[i10]) if i90 > i10 else float("nan")
    # exponential approach: fit ln(1 - (y-base)/amp) over 10..90 %
    frac = (yr - base) / amp if amp else np.zeros_like(yr)
    sel = (frac > 0.1) & (frac < 0.9)
    tau = float("nan")
    if sel.sum() > 5:
        k, _ = np.polyfit(tr[sel], np.log(1 - frac[sel]), 1)
        tau = float(-1 / k) if k < 0 else float("nan")
    return {
        "baseline_v": base,
        "plateau_v": plateau,
        "amplitude_v": amp,
        "rise_10_90_s": rise,
        "tau_s": tau,
        "bandwidth_from_rise_hz": float(0.35 / rise) if np.isfinite(rise) and rise > 0 else None,
        "bandwidth_from_tau_hz": float(1 / (2 * np.pi * tau)) if np.isfinite(tau) else None,
    }


def step_opx(b: Bench, out: Path) -> dict:
    b.qdac.set("ch01", 0.0)
    expected = OPX_PULSE_V / OPX_NOMINAL_DIVISION
    b.front_panel(0.05, trigger_level_v=expected / 2)
    b.opx.play("ao1", pulse_train(OPX_PULSE_ON_S, OPX_PULSE_PERIOD_S, OPX_PULSE_V), SAMPLE_RATE)
    time.sleep(OPX_SETTLE_S)
    t, y = capture(b.scope, -0.5 * OPX_PULSE_ON_S, 1.5 * OPX_PULSE_ON_S, 4000)
    np.savez_compressed(out / "step_opx.npz", t=t, y=y)
    m = edge_metrics(t, y, OPX_PULSE_ON_S)
    # the edge itself at 1 ns: a second record zoomed on the rising edge
    tz, yz = capture(b.scope, -1e-6, 3e-6, 4000)
    b.opx.stop("ao1")
    np.savez_compressed(out / "step_opx_edge.npz", t=tz, y=yz)
    base, plat = m["baseline_v"], m["plateau_v"]
    frac = (yz - base) / (plat - base) if plat != base else np.zeros_like(yz)
    i10, i90 = int(np.argmax(frac >= 0.1)), int(np.argmax(frac >= 0.9))
    m["rise_10_90_s"] = float(tz[i90] - tz[i10]) if i90 > i10 else float("nan")
    m["bandwidth_from_rise_hz"] = float(0.35 / m["rise_10_90_s"]) if i90 > i10 else None
    sel = (frac > 0.1) & (frac < 0.9) & (tz >= 0)
    if sel.sum() > 5:
        k, _ = np.polyfit(tz[sel], np.log(1 - frac[sel]), 1)
        m["tau_s"] = float(-1 / k) if k < 0 else float("nan")
        m["bandwidth_from_tau_hz"] = float(1 / (2 * np.pi * m["tau_s"])) if k < 0 else None
    early = float(np.mean(yz[(tz > 1e-6) & (tz < 3e-6)]))
    m["droop_percent_over_pulse"] = (
        float((1 - (plat - base) / (early - base)) * 100) if early != base else None
    )
    m.update(
        {
            "pulse_v": OPX_PULSE_V,
            "gain_into_1M": m["amplitude_v"] / OPX_PULSE_V,
            "division_into_1M": OPX_PULSE_V / m["amplitude_v"] if m["amplitude_v"] else None,
            "nominal_division": OPX_NOMINAL_DIVISION,
        }
    )
    return m


def superposition(b: Bench, dc: dict, step: dict) -> dict:
    expected = OPX_PULSE_V / OPX_NOMINAL_DIVISION
    b.front_panel(0.1, trigger_level_v=0.5 * dc["gain_into_1M"] + expected / 2)
    b.qdac.set("ch01", 0.5)
    time.sleep(SETTLE_S)
    b.opx.play("ao1", pulse_train(OPX_PULSE_ON_S, OPX_PULSE_PERIOD_S, OPX_PULSE_V), SAMPLE_RATE)
    time.sleep(OPX_SETTLE_S)
    t, y = capture(b.scope, -0.5 * OPX_PULSE_ON_S, 1.5 * OPX_PULSE_ON_S, 4000)
    b.opx.stop("ao1")
    b.qdac.set("ch01", 0.0)
    m = edge_metrics(t, y, OPX_PULSE_ON_S)
    return {
        "qdac_v": 0.5,
        "baseline_v": m["baseline_v"],
        "baseline_expected_v": 0.5 * dc["gain_into_1M"] + dc["offset_mv"] * 1e-3,
        "pulse_amplitude_v": m["amplitude_v"],
        "pulse_amplitude_alone_v": step["amplitude_v"],
    }


def step_qdac(b: Bench, out: Path) -> dict:
    """The DC side's time constant: a 0 -> 1 V QDAC step, the scope edge-triggered (NORMAL sweep) with
    the step applied from a thread once the capture is armed."""
    import threading

    b.opx.stop("ao1")
    b.qdac.set("ch01", 0.0)
    b.front_panel(0.1, trigger_level_v=0.1)
    b._scpi.write(":CHANnel1:OFFSet 0.2")
    b._scpi.write(":TRIGger:SWEep NORMal")
    threading.Thread(target=lambda: (time.sleep(1.5), b.qdac.set("ch01", 1.0)), daemon=True).start()
    try:
        t, y = capture(b.scope, -20e-3, 180e-3, 2000)
    finally:
        b.qdac.set("ch01", 0.0)
        b._scpi.write(":TRIGger:SWEep AUTO")
        b._scpi.write(":CHANnel1:OFFSet 0")
    np.savez_compressed(out / "step_qdac.npz", t=t, y=y)
    base, plat = float(np.mean(y[t < -5e-3])), float(np.mean(y[t > 150e-3]))
    frac = (y - base) / (plat - base)
    i10, i90 = int(np.argmax(frac >= 0.1)), int(np.argmax(frac >= 0.9))
    sel = (frac > 0.05) & (frac < 0.95) & (t > 0)
    tau = float("nan")
    if sel.sum() > 5:
        k, _ = np.polyfit(t[sel], np.log(1 - frac[sel]), 1)
        tau = float(-1 / k) if k < 0 else float("nan")
    return {
        "step_v": 1.0,
        "baseline_v": base,
        "final_v": plat,
        "division_into_1M": 1.0 / (plat - base),
        "rise_10_90_s": float(t[i90] - t[i10]),
        "tau_s": tau,
        "bandwidth_from_tau_hz": float(1 / (2 * np.pi * tau)) if np.isfinite(tau) else None,
        "settled_fraction_at_ms": {
            str(ms): float(frac[np.searchsorted(t, ms * 1e-3)]) for ms in (1, 10, 50)
        },
    }


def sines_opx(b: Bench, dc_gain_opx: float, out: Path) -> dict:
    b.qdac.set("ch01", 0.0)
    b.front_panel(0.1)
    rows = []
    for hz in OPX_SINE_HZ:
        periods = max(1, round(50e-6 * hz))  # whole periods in <= ~50 us of waveform memory
        n = round(periods / hz * SAMPLE_RATE)
        wave = OPX_SINE_V * np.sin(2 * np.pi * hz * np.arange(n) / SAMPLE_RATE)
        b.opx.play("ao1", wave, SAMPLE_RATE)
        time.sleep(OPX_SETTLE_S)
        span = 4 / hz
        t, y = capture(b.scope, 0.0, span, 4000)
        b.opx.stop("ao1")
        yy = y - y.mean()
        spectrum, freqs = np.abs(np.fft.rfft(yy)), np.fft.rfftfreq(yy.size, t[1] - t[0])
        amp = float(np.sqrt(2) * np.std(yy))
        rows.append(
            {
                "hz": hz,
                "peak_hz_on_scope": float(freqs[np.argmax(spectrum[1:]) + 1]),
                "mean_v": float(y.mean()),
                "amplitude_v": amp,
                "gain": amp / OPX_SINE_V,
                "rel_to_dc_db": float(20 * np.log10(amp / OPX_SINE_V / dc_gain_opx)),
                "clipped": bool(np.abs(y).max() >= 0.39),
            }
        )
        np.savez_compressed(out / f"sine_opx_{int(hz)}.npz", t=t, y=y)
    return {"drive_v": OPX_SINE_V, "rows": rows, "minus_3db_hz": _minus_3db(rows)}


def sines_qdac(b: Bench, dc_gain_qdac: float, out: Path) -> dict:
    b.opx.stop("ao1")
    b.front_panel(0.1)
    rows = []
    for hz in QDAC_SINE_HZ:
        b.qdac_sine(hz, QDAC_SINE_VPP)
        time.sleep(max(0.5, 3 / hz))
        t, y = capture(b.scope, 0.0, 4 / hz, 2000)
        amp = float(np.sqrt(2) * np.std(y))
        gain = amp / (QDAC_SINE_VPP / 2)
        rows.append(
            {
                "hz": hz,
                "amplitude_v": amp,
                "gain": gain,
                "rel_to_dc_db": float(20 * np.log10(gain / dc_gain_qdac)),
            }
        )
        np.savez_compressed(out / f"sine_qdac_{int(hz)}.npz", t=t, y=y)
    b.qdac_sine_stop()
    return {"drive_vpp": QDAC_SINE_VPP, "rows": rows, "minus_3db_hz": _minus_3db(rows)}


def _minus_3db(rows: list[dict]) -> float | None:
    """Interpolated frequency where the response crosses −3 dB relative to DC, if it does."""
    for a, b_ in zip(rows, rows[1:], strict=False):
        if a["rel_to_dc_db"] >= -3 > b_["rel_to_dc_db"]:
            f = np.interp(
                -3, [b_["rel_to_dc_db"], a["rel_to_dc_db"]], [np.log10(b_["hz"]), np.log10(a["hz"])]
            )
            return float(10**f)
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--qdac", required=True)
    p.add_argument("--opx", required=True)
    p.add_argument("--fem", type=int, default=1)
    p.add_argument("--scope", required=True)
    p.add_argument(
        "--meter-mv", type=float, default=None, help="hand meter at the board output, QDAC at 1 V"
    )
    p.add_argument(
        "--sections", default="dc_qdac,step_qdac,step_opx,superposition,sines_opx,sines_qdac"
    )
    p.add_argument("--out", type=Path, default=Path("bench/fixtures/probe03"))
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    wanted = a.sections.split(",")
    b = Bench(a)
    findings: dict = {}
    if (a.out / "combiner.json").exists():  # sections accumulate across runs
        findings = json.loads((a.out / "combiner.json").read_text())
    findings["run_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        if "dc_qdac" in wanted:
            findings["dc_qdac"] = dc_qdac(b)
            if a.meter_mv:
                g = findings["dc_qdac"]["gain_into_1M"]
                r_out = 1e6 * (a.meter_mv * 1e-3 / g - 1)
                findings["dc_qdac"]["meter_mv_at_1v"] = a.meter_mv
                findings["dc_qdac"]["output_impedance_ohm_from_meter_vs_scope"] = float(r_out)
                findings["dc_qdac"]["division_open_circuit"] = float(1 / (a.meter_mv * 1e-3))
        if "step_qdac" in wanted:
            findings["step_qdac"] = step_qdac(b, a.out)
        if "step_opx" in wanted:
            findings["step_opx"] = step_opx(b, a.out)
        if "superposition" in wanted and "dc_qdac" in findings and "step_opx" in findings:
            findings["superposition"] = superposition(b, findings["dc_qdac"], findings["step_opx"])
        if "sines_opx" in wanted:
            g = findings.get("step_opx", {}).get("gain_into_1M") or (1 / OPX_NOMINAL_DIVISION)
            findings["sines_opx"] = sines_opx(b, g, a.out)
        if "sines_qdac" in wanted:
            g = findings.get("dc_qdac", {}).get("gain_into_1M") or (1 / QDAC_NOMINAL_DIVISION)
            findings["sines_qdac"] = sines_qdac(b, g, a.out)
    finally:
        b.close()
    (a.out / "combiner.json").write_text(json.dumps(findings, indent=2))
    print(json.dumps(findings, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
