"""Probe 04 — how fast the QDAC-II settles after `set` (docs/probes/04-qdac-settling.md).

The question: in a stepped sweep with no trigger between the DC source and the sequencer, how long
must the executor wait after `LevelSource.set` before a pulse sequence and its acquisition may start?
That is `ChannelMap.settle_s` for a QDAC channel, and it has two parts the sweep cannot see:

1. **command latency** — from `set()` returning on the host to the output starting to move;
2. **analog settling** — from the output starting to move to it being within tolerance of the final
   value, set by the channel's output filter (QDAC-II: DC ≈ 10 Hz, MED ≈ 10 kHz, HIGH ≈ 300 kHz
   nominal low-pass; the manual's figures, measured here) and the step size.

Wiring: QDAC ch{N} → scope ch{M} directly (DC, 1 MΩ), no board in between (the combiner's 20 Hz DC
side would hide everything; Probe 03). Both instruments through their drivers; the scope's trigger,
single-shot acquisition and waveform read go over the driver's SCPI transport because the protocol
(ADR 0021) leaves the trigger to the user and `arm` would start its own acquisition.

Per (filter, step): the channel sits at 0 V; the scope is armed single-shot on a rising edge at half
the step; `set(step)` is timed on the host; the scope's trigger event register is polled with host
timestamps (the trigger time to ~1 ms, the poll's round trip); the record is read and the settling
times extracted: 10–90 % rise, time to within 1 % and within 0.1 % (or 1 mV, whichever is larger) of
the final level, and the overshoot. Records are saved as `.npz`; findings as `settling.json`.

    uv run python bench/probes/probe04/qdac_settling.py --qdac "ASRL/dev/cu.usbserial-NNNN::INSTR" \
        --scope "TCPIP::<scope>::5025::SOCKET" [--qdac-channel 2] [--scope-channel 2] \
        [--filters dc,med,high] [--steps 0.01,0.1,1.0] [--out bench/fixtures/probe04]
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from qdt_schemas.stand import ChannelMap, InstrumentConfig

FILTERS = ("dc", "med", "high")
NOMINAL_CUTOFF_HZ = {"dc": 10.0, "med": 10e3, "high": 300e3}
"""QDAC-II output filter nominal −3 dB frequencies (manual); the record windows are sized from them."""
WINDOW_S = {"dc": 0.25, "med": 1e-3, "high": 40e-6}
"""Record length per filter: ≈ 15 time constants of the nominal cutoff, plus a pre-trigger tenth."""
POINTS = 4000
REPEATS = 3
TRIGGER_TIMEOUT_S = 3.0


class Bench:
    def __init__(self, a):
        from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX
        from qdt_lab.drivers.qdevil.qdac2 import QDac2

        self.n, self.m = a.qdac_channel, a.scope_channel
        self.qdac = QDac2.from_config(
            InstrumentConfig(
                id="dac0",
                backend="qdac2",
                capabilities=("level_source",),
                settings={"address": a.qdac},
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
            (ChannelMap(logical="ch", instrument="scope0", channel=str(self.m), quantity="voltage"),),
        )
        self._s = self.scope._t  # trigger, single-shot, waveform read: outside the protocol
        self._q = self.qdac._t  # the output filter: outside the protocol

    # --- QDAC ---------------------------------------------------------------------------------------

    def filter(self) -> str:
        return self._q.query(f"sour{self.n}:filt?").strip().lower()

    def set_filter(self, name: str) -> None:
        self._q.write(f"sour{self.n}:filt {name}")

    def set_timed(self, volts: float) -> tuple[float, float]:
        """`set` on the channel; returns (host time before, host time after) in perf_counter seconds."""
        t0 = time.perf_counter()
        self.qdac.set(f"ch{self.n:02d}", volts)
        return t0, time.perf_counter()

    # --- scope --------------------------------------------------------------------------------------

    def front_panel(self, step: float, window_s: float) -> None:
        w, m = self._s.write, self.m
        w(f":CHANnel{m}:DISPlay 1")
        w(f":CHANnel{m}:COUPling DC")
        w(f":CHANnel{m}:IMPedance ONEMeg")
        w(f":CHANnel{m}:PROBe 1")
        w(f":CHANnel{m}:SCALe {step / 5:.6g}")  # the step spans five of eight divisions
        w(f":CHANnel{m}:OFFSet {step / 2:.6g}")
        w(":TIMebase:REFerence LEFT")
        w(f":TIMebase:RANGe {window_s:.9g}")
        w(f":TIMebase:POSition {-window_s / 10:.9g}")  # the trigger one division in from the left
        w(":TRIGger:MODE EDGE")
        w(f":TRIGger:EDGE:SOURce CHANnel{m}")
        w(":TRIGger:EDGE:SLOPe POSitive")
        w(":TRIGger:EDGE:COUPling DC")
        w(f":TRIGger:EDGE:LEVel {step / 2:.6g}")
        w(":TRIGger:SWEep NORMal")  # single-shot must wait for the edge, not auto-trigger
        w(f":WAVeform:SOURce CHANnel{m}")
        w(":WAVeform:FORMat WORD")
        w(":WAVeform:BYTeorder LSBFirst")
        w(":WAVeform:UNSigned 0")
        w(":WAVeform:POINts:MODE RAW")
        w(f":WAVeform:POINts {POINTS}")

    def arm_single(self) -> None:
        self._s.query(":TER?")  # clear a stale trigger event
        self._s.write(":SINGle")
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < TRIGGER_TIMEOUT_S:
            if self._s.query(":AER?").strip() == "1":
                return
            time.sleep(0.01)
        raise TimeoutError("the scope did not arm")

    def wait_trigger(self) -> float | None:
        """Poll the trigger event register; the host time at which it first read 1 (None: timeout)."""
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < TRIGGER_TIMEOUT_S:
            if self._s.query(":TER?").strip() == "1":
                return time.perf_counter()
        return None

    def read(self) -> tuple[np.ndarray, np.ndarray]:
        """The acquired record as (time relative to the trigger, volts)."""
        self._s.query("*OPC?")
        pre = [p.strip() for p in self._s.query(":WAVeform:PREamble?").split(",")]
        xinc, xorig, xref = float(pre[4]), float(pre[5]), float(pre[6])
        yinc, yorig, yref = float(pre[7]), float(pre[8]), float(pre[9])
        codes = self._s.query_block(":WAVeform:DATA?", "<i2")
        return (np.arange(codes.size) - xref) * xinc + xorig, (codes.astype(np.float64) - yref) * yinc + yorig

    def close(self) -> None:
        try:
            self.qdac.set(f"ch{self.n:02d}", 0.0)
            self._s.write(":TRIGger:SWEep AUTO")
            self._s.write(":RUN")
        finally:
            self.scope.close()
            self.qdac.close()


def settling(t: np.ndarray, y: np.ndarray, step: float) -> dict:
    """Settling metrics of a 0 → `step` record: base and final levels, 10–90 % rise, time to stay
    within 1 % and within max(0.1 %, 1 mV) of the final level, overshoot."""
    pre = t < -0.02 * (t[-1] - t[0])
    base = float(np.mean(y[pre])) if pre.sum() > 5 else float(y[0])
    tail = t > t[-1] - 0.1 * (t[-1] - t[0])
    final = float(np.mean(y[tail]))
    amp = final - base
    after = t >= 0
    ta, ya = t[after], y[after]
    frac = (ya - base) / amp if amp else np.zeros_like(ya)
    i10, i90 = int(np.argmax(frac >= 0.1)), int(np.argmax(frac >= 0.9))
    rise = float(ta[i90] - ta[i10]) if i90 > i10 else float("nan")

    def settled_within(tol_v: float) -> float:
        outside = np.flatnonzero(np.abs(ya - final) > tol_v)
        return float(ta[outside[-1] + 1]) if outside.size and outside[-1] + 1 < ta.size else (float(ta[0]) if not outside.size else float("nan"))

    return {
        "base_v": base,
        "final_v": final,
        "amplitude_v": amp,
        "rise_10_90_s": rise,
        "settle_1pct_s": settled_within(0.01 * abs(amp)),
        "settle_fine_s": settled_within(max(1e-3 * abs(amp), 1e-3)),
        "fine_tolerance_v": max(1e-3 * abs(amp), 1e-3),
        "overshoot_pct": float(100 * (ya.max() - final) / amp) if amp > 0 else None,
        "noise_rms_v": float(np.std(y[tail])),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--qdac", required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--qdac-channel", type=int, default=2)
    p.add_argument("--scope-channel", type=int, default=2)
    p.add_argument("--filters", default=",".join(FILTERS))
    p.add_argument("--steps", default="0.01,0.1,1.0")
    p.add_argument("--out", type=Path, default=Path("bench/fixtures/probe04"))
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    b = Bench(a)
    findings: dict = {"run_at": datetime.now(UTC).isoformat(), "qdac_channel": a.qdac_channel, "rows": []}
    try:
        original = b.filter()
        findings["default_filter"] = original
        print(f"QDAC ch{a.qdac_channel:02d} default output filter: {original}")
        for name in [f.strip() for f in a.filters.split(",") if f.strip()]:
            b.set_filter(name)
            time.sleep(0.2)
            print(f"filter {name} (reads back {b.filter()})")
            for step in [float(s) for s in a.steps.split(",") if s.strip()]:
                window = WINDOW_S[name]
                rows = []
                for k in range(REPEATS):
                    b.qdac.set(f"ch{a.qdac_channel:02d}", 0.0)
                    time.sleep(max(0.05, 5 / NOMINAL_CUTOFF_HZ[name]))
                    b.front_panel(step, window)
                    b.arm_single()
                    t_call, t_return = b.set_timed(step)
                    t_trig = b.wait_trigger()
                    if t_trig is None:
                        print(f"  step {step} V: no trigger within {TRIGGER_TIMEOUT_S} s")
                        continue
                    t, y = b.read()
                    m = settling(t, y, step)
                    m.update(
                        {
                            "set_call_s": t_return - t_call,
                            "set_return_to_trigger_seen_s": t_trig - t_return,
                            "poll_resolution_s": None,
                        }
                    )
                    rows.append(m)
                    np.savez_compressed(a.out / f"step_{name}_{step:g}V_{k}.npz", t=t, y=y)
                if not rows:
                    continue
                med = {k: float(np.median([r[k] for r in rows if r[k] is not None])) for k in rows[0] if k != "poll_resolution_s"}
                med.update({"filter": name, "step_v": step, "repeats": len(rows), "window_s": window})
                findings["rows"].append(med)
                print(
                    f"  step {step:g} V: set() {med['set_call_s'] * 1e3:.2f} ms, trigger seen {med['set_return_to_trigger_seen_s'] * 1e3:.1f} ms after return, "
                    f"rise {med['rise_10_90_s'] * 1e6:.1f} µs, settled 1 % at {med['settle_1pct_s'] * 1e6:.1f} µs, "
                    f"fine ({med['fine_tolerance_v'] * 1e3:.1f} mV) at {med['settle_fine_s'] * 1e6:.1f} µs, overshoot {med['overshoot_pct']:.2f} %"
                )
        b.set_filter(original)
        (a.out / "settling.json").write_text(json.dumps(findings, indent=2) + "\n")
        print(f"wrote {a.out / 'settling.json'}")
    finally:
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
