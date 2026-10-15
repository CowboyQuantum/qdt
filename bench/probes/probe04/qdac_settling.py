"""Probe 04 — how fast the QDAC-II settles after `set` (docs/probes/04-qdac-settling.md).

The question: in a stepped sweep with no trigger between the DC source and the sequencer, how long
must the executor wait after `LevelSource.set` before a pulse sequence and its acquisition may start?
That is `ChannelMap.settle_s` for a QDAC channel, and it has two parts the sweep cannot see:

1. **command latency** — from `set()` returning on the host (the driver writes `sour<n>:volt` and does
   not wait for an acknowledgement) to the output starting to move;
2. **analog settling** — from the output starting to move to it being within tolerance of the final
   value: the channel's output filter (QDAC-II: DC, MED, HIGH; nominal 10 Hz, 10 kHz, 300 kHz) and the
   step size.

Wiring: QDAC ch{N} → scope ch{M} directly (DC, 1 MΩ), no board in between (the combiner's 20 Hz DC
side would hide everything; Probe 03). Both instruments through their drivers; the scope's trigger,
single-shot acquisition and waveform read go over the driver's SCPI transport because the protocol
(ADR 0021) leaves the trigger to the user and `arm` would start its own acquisition.

Sections:
- `steps`: per (filter, step), the channel sits at 0 V; the scope is armed single-shot on a rising edge
  at half the step, at two timebases (a fine one for the edge, a long one for any slow tail); `set` is
  timed on the host; the record gives 10–90 % rise, time to within 1 % and within max(0.1 %, 1 mV) of
  the final level, and the overshoot.
- `latency`: the scope's trigger event register is polled around `set`; each repeat brackets the edge
  between the last poll that read 0 and the first that read 1 (the poll is one query round trip, ≈ 5 ms
  on this scope); the brackets' intersection over the repeats is the latency estimate.
- `jitter`: two `set`s a known host interval apart; the two edges' separation in one record against
  the host interval gives the latency's variation, independent of its mean.

Records are saved as `.npz`; findings as `settling.json`.

    uv run python bench/probes/probe04/qdac_settling.py --qdac "ASRL/dev/cu.usbserial-NNNN::INSTR" \
        --scope "TCPIP::<scope>::5025::SOCKET" [--qdac-channel 2] [--scope-channel 2] \
        [--filters dc,med,high] [--steps 0.01,0.1,1.0] [--sections steps,latency,jitter] [--out ...]
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
"""QDAC-II output filter nominal −3 dB frequencies (manual)."""
FINE_WINDOW_S = 400e-6
"""The edge: 100 ns per sample over 4000 points."""
LONG_WINDOW_S = {"dc": 0.25, "med": 2e-3, "high": 2e-3}
"""Any slow tail: ≈ 15 time constants of the nominal cutoff for DC; 2 ms otherwise."""
POINTS = 4000
REPEATS = 3
LATENCY_REPEATS = 12
JITTER_REPEATS = 6
JITTER_INTERVAL_S = 0.010
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
            (
                ChannelMap(
                    logical="ch", instrument="scope0", channel=str(self.m), quantity="voltage"
                ),
            ),
        )
        self._s = self.scope._t  # trigger, single-shot, waveform read: outside the protocol
        self._s._r.timeout = 20000
        self._q = self.qdac._t  # the output filter: outside the protocol

    # --- QDAC ---------------------------------------------------------------------------------------

    @property
    def channel(self) -> str:
        return f"ch{self.n:02d}"

    def filter(self) -> str:
        return self._q.query(f"sour{self.n}:filt?").strip().lower()

    def set_filter(self, name: str) -> None:
        self._q.write(f"sour{self.n}:filt {name}")
        time.sleep(0.5)
        err = self._q.query("syst:err?").strip()
        if not err.startswith("0"):
            print(f"  QDAC error after filter {name}: {err}")

    def set_timed(self, volts: float) -> tuple[float, float]:
        """`set` on the channel; (host time before, host time after), perf_counter seconds."""
        t0 = time.perf_counter()
        self.qdac.set(self.channel, volts)
        return t0, time.perf_counter()

    # --- scope --------------------------------------------------------------------------------------

    def front_panel(self, scale: float, offset: float, level: float, window_s: float) -> None:
        w, m = self._s.write, self.m
        w(":STOP")  # a single-shot still waiting for its edge would block *OPC? below
        for c in (
            f":CHANnel{m}:DISPlay 1",
            f":CHANnel{m}:COUPling DC",
            f":CHANnel{m}:IMPedance ONEMeg",
            f":CHANnel{m}:PROBe 1",
            f":CHANnel{m}:SCALe {scale:.6g}",
            f":CHANnel{m}:OFFSet {offset:.6g}",
            ":TIMebase:REFerence LEFT",
            f":TIMebase:RANGe {window_s:.9g}",
            f":TIMebase:POSition {-window_s / 10:.9g}",  # the trigger one division in from the left
            ":TRIGger:MODE EDGE",
            f":TRIGger:EDGE:SOURce CHANnel{m}",
            ":TRIGger:EDGE:SLOPe POSitive",
            ":TRIGger:EDGE:COUPling DC",
            f":TRIGger:EDGE:LEVel {level:.6g}",
            ":TRIGger:SWEep NORMal",  # single-shot must wait for the edge, not auto-trigger
            f":WAVeform:SOURce CHANnel{m}",
            ":WAVeform:FORMat WORD",
            ":WAVeform:BYTeorder LSBFirst",
            ":WAVeform:UNSigned 0",
            ":WAVeform:POINts:MODE RAW",
            f":WAVeform:POINts {POINTS}",
        ):
            w(c)
        self._s.query("*OPC?")
        err = self._s.query(":SYSTem:ERRor?").strip()
        if not err.startswith("+0"):
            print(f"  scope error after setup: {err}")

    def arm_single(self) -> None:
        """Arm one acquisition and wait until the scope says it is armed (both event registers are
        cleared first: a stale arm bit let a step fire before the scope was ready)."""
        self._s.query(":AER?")
        self._s.query(":TER?")
        self._s.write(":SINGle")
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < TRIGGER_TIMEOUT_S:
            if int(float(self._s.query(":AER?"))) == 1:
                return
            time.sleep(0.005)
        raise TimeoutError("the scope did not arm")

    def triggered(self) -> bool:
        return int(float(self._s.query(":TER?"))) == 1

    def wait_trigger(self) -> bool:
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < TRIGGER_TIMEOUT_S:
            if self.triggered():
                return True
        return False

    def read(self) -> tuple[np.ndarray, np.ndarray]:
        """The acquired record as (time relative to the trigger, volts)."""
        self._s.query("*OPC?")
        pre = [p.strip() for p in self._s.query(":WAVeform:PREamble?").split(",")]
        xinc, xorig, xref = float(pre[4]), float(pre[5]), float(pre[6])
        yinc, yorig, yref = float(pre[7]), float(pre[8]), float(pre[9])
        codes = self._s.query_block(":WAVeform:DATA?", "<i2")
        t = (np.arange(codes.size) - xref) * xinc + xorig
        return t, (codes.astype(np.float64) - yref) * yinc + yorig

    def close(self) -> None:
        try:
            self.qdac.set(self.channel, 0.0)
            self._s.write(":TRIGger:SWEep AUTO")
            self._s.write(":RUN")
        finally:
            self.scope.close()
            self.qdac.close()


def settling(t: np.ndarray, y: np.ndarray, step: float) -> dict:
    """Settling metrics of a 0 → `step` record: base and final levels, 10–90 % rise, time (from the
    trigger) after which the record stays within 1 % and within max(0.1 %, 1 mV) of the final level,
    overshoot, noise."""
    span = t[-1] - t[0]
    pre = t < -0.02 * span
    base = float(np.mean(y[pre])) if pre.sum() > 5 else float(y[0])
    tail = t > t[-1] - 0.1 * span
    final = float(np.mean(y[tail]))
    amp = final - base
    after = t >= t[0]  # the whole record: a slow edge may start before the trigger point
    ta, ya = t[after], y[after]
    frac = (ya - base) / amp if amp else np.zeros_like(ya)
    i10, i90 = int(np.argmax(frac >= 0.1)), int(np.argmax(frac >= 0.9))
    rise = float(ta[i90] - ta[i10]) if i90 > i10 else float("nan")

    def settled_after(tol_v: float) -> float:
        outside = np.flatnonzero(np.abs(ya - final) > tol_v)
        if outside.size == 0:
            return float(ta[0])
        return float(ta[outside[-1] + 1]) if outside[-1] + 1 < ta.size else float("nan")

    fine = max(1e-3 * abs(amp), 1e-3)
    return {
        "base_v": base,
        "final_v": final,
        "amplitude_v": amp,
        "t10_s": float(ta[i10]),
        "rise_10_90_s": rise,
        "settle_1pct_s": settled_after(0.01 * abs(amp)),
        "settle_fine_s": settled_after(fine),
        "fine_tolerance_v": fine,
        "overshoot_pct": float(100 * (ya.max() - final) / amp) if amp > 0 else None,
        "noise_rms_v": float(np.std(y[tail])),
    }


def median_rows(rows: list[dict]) -> dict:
    out = {}
    for k in rows[0]:
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float)) and r[k] is not None]
        out[k] = float(np.nanmedian(vals)) if vals else None
    return out


def section_steps(b: Bench, a, findings: dict) -> None:
    for name in a.filters:
        b.set_filter(name)
        print(f"filter {name} (reads back {b.filter()})")
        for step in a.steps:
            for window, tag in ((FINE_WINDOW_S, "fine"), (LONG_WINDOW_S[name], "long")):
                rows = []
                for k in range(REPEATS):
                    for attempt in range(2):  # a missed trigger is retried once, and reported
                        b.qdac.set(b.channel, 0.0)
                        time.sleep(max(0.1, 10 / NOMINAL_CUTOFF_HZ[name]))
                        b.front_panel(step / 5, step / 2, step / 2, window)
                        b.arm_single()
                        t_call, t_return = b.set_timed(step)
                        if b.wait_trigger():
                            break
                        print(
                            f"  {name} {step:g} V {tag} rep {k}: no trigger within {TRIGGER_TIMEOUT_S} s (attempt {attempt + 1}); QDAC reads {b.qdac.get(b.channel):.4f} V"
                        )
                        b._s.write(":STOP")
                    else:
                        continue
                    t, y = b.read()
                    m = settling(t, y, step)
                    m["set_call_s"] = t_return - t_call
                    rows.append(m)
                    np.savez_compressed(a.out / f"step_{name}_{step:g}V_{tag}_{k}.npz", t=t, y=y)
                if not rows:
                    continue
                med = median_rows(rows)
                med.update(
                    {
                        "filter": name,
                        "step_v": step,
                        "window": tag,
                        "window_s": window,
                        "repeats": len(rows),
                    }
                )
                findings["steps"].append(med)
                print(
                    f"  {step:g} V {tag:4s}: rise {med['rise_10_90_s'] * 1e6:8.2f} µs, within 1 % after "
                    f"{med['settle_1pct_s'] * 1e6:8.2f} µs, within {med['fine_tolerance_v'] * 1e3:.1f} mV after "
                    f"{med['settle_fine_s'] * 1e6:8.2f} µs, overshoot {med['overshoot_pct']:.2f} %, noise {med['noise_rms_v'] * 1e3:.2f} mV rms"
                )


def section_latency(b: Bench, a, findings: dict) -> None:
    """Bracket the edge between the last 0 and the first 1 of the trigger event register around `set`."""
    b.set_filter("high")
    step = 1.0
    b.qdac.set(b.channel, 0.0)
    time.sleep(0.2)
    b.front_panel(step / 5, step / 2, step / 2, 2e-3)
    rtt = []
    for _ in range(5):
        t0 = time.perf_counter()
        b.triggered()
        rtt.append(time.perf_counter() - t0)
    poll = float(np.median(rtt))
    print(f"latency: scope trigger-register poll takes {poll * 1e3:.1f} ms")
    lows, highs, calls = [], [], []
    for k in range(LATENCY_REPEATS):
        b.qdac.set(b.channel, 0.0)
        time.sleep(0.3)
        b.arm_single()
        # one poll before the set, so the bracket's lower edge is known to be before it
        t_poll0 = time.perf_counter()
        if b.triggered():
            print(f"  rep {k}: triggered before the set (noise at the level?)")
            b._s.write(":STOP")
            continue
        t_call, t_return = b.set_timed(step)
        last_zero, first_one = t_poll0, None
        t_limit = time.perf_counter() + TRIGGER_TIMEOUT_S
        while time.perf_counter() < t_limit:
            t_send = time.perf_counter()
            if b.triggered():
                first_one = t_send  # the register was read after this send: the edge was before it
                break
            last_zero = t_send  # the register was still 0 when this poll was answered
        if first_one is None:
            print(f"  rep {k}: no trigger")
            b._s.write(":STOP")
            continue
        b.read()
        lo, hi = last_zero - t_return, first_one + poll - t_return
        lows.append(lo)
        highs.append(hi)
        calls.append(t_return - t_call)
        print(
            f"  rep {k}: set() took {(t_return - t_call) * 1e3:.2f} ms; edge between {lo * 1e3:+.1f} and {hi * 1e3:+.1f} ms after it returned"
        )
    if lows:
        findings["latency"] = {
            "poll_round_trip_s": poll,
            "set_call_s_median": float(np.median(calls)),
            "edge_after_return_lower_s": float(max(lows)),
            "edge_after_return_upper_s": float(min(highs)),
            "repeats": len(lows),
        }
        print(
            f"  → the output edge follows set()'s return by between {max(lows) * 1e3:.1f} and {min(highs) * 1e3:.1f} ms "
            f"(intersection of {len(lows)} brackets; set() itself takes {np.median(calls) * 1e3:.2f} ms)"
        )


def section_jitter(b: Bench, a, findings: dict) -> None:
    """Two sets `JITTER_INTERVAL_S` apart on the host; their edges' separation in one record."""
    b.set_filter("high")
    b.qdac.set(b.channel, 0.0)
    time.sleep(0.2)
    b.front_panel(0.25, 0.5, 0.25, 4 * JITTER_INTERVAL_S)
    rows = []
    for k in range(JITTER_REPEATS):
        b.qdac.set(b.channel, 0.0)
        time.sleep(0.3)
        b.arm_single()
        _, t1 = b.set_timed(0.5)
        while time.perf_counter() - t1 < JITTER_INTERVAL_S:
            pass
        _, t2 = b.set_timed(1.0)
        if not b.wait_trigger():
            print(f"  rep {k}: no trigger")
            b._s.write(":STOP")
            continue
        t, y = b.read()
        e1 = np.flatnonzero(y > 0.25)
        e2 = np.flatnonzero(y > 0.75)
        if e1.size == 0 or e2.size == 0:
            print(f"  rep {k}: edges not found (max {y.max():.3f} V)")
            continue
        host, scope = t2 - t1, float(t[e2[0]] - t[e1[0]])
        rows.append(
            {"host_interval_s": host, "scope_interval_s": scope, "difference_s": scope - host}
        )
        np.savez_compressed(a.out / f"jitter_{k}.npz", t=t, y=y)
        print(
            f"  rep {k}: host interval {host * 1e3:.2f} ms, edges {scope * 1e3:.2f} ms apart on the scope ({(scope - host) * 1e3:+.2f} ms)"
        )
    if rows:
        d = np.array([r["difference_s"] for r in rows])
        findings["jitter"] = {
            "interval_s": JITTER_INTERVAL_S,
            "difference_s_median": float(np.median(d)),
            "difference_s_min": float(d.min()),
            "difference_s_max": float(d.max()),
            "repeats": len(rows),
        }
        print(
            f"  → latency variation between two sets: {d.min() * 1e3:+.2f} to {d.max() * 1e3:+.2f} ms over {len(rows)} repeats"
        )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--qdac", required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--qdac-channel", type=int, default=2)
    p.add_argument("--scope-channel", type=int, default=2)
    p.add_argument("--filters", default=",".join(FILTERS))
    p.add_argument("--steps", default="0.01,0.1,1.0")
    p.add_argument("--sections", default="steps,latency,jitter")
    p.add_argument("--out", type=Path, default=Path("bench/fixtures/probe04"))
    a = p.parse_args()
    a.filters = [f.strip() for f in a.filters.split(",") if f.strip()]
    a.steps = [float(s) for s in a.steps.split(",") if s.strip()]
    a.out.mkdir(parents=True, exist_ok=True)
    wanted = {s.strip() for s in a.sections.split(",")}
    b = Bench(a)
    findings: dict = {
        "run_at": datetime.now(UTC).isoformat(),
        "qdac_channel": a.qdac_channel,
        "steps": [],
    }
    original = b.filter()
    findings["default_filter"] = original
    print(f"QDAC {b.channel} output filter before the probe: {original}")
    try:
        if "steps" in wanted:
            section_steps(b, a, findings)
        if "latency" in wanted:
            section_latency(b, a, findings)
        if "jitter" in wanted:
            section_jitter(b, a, findings)
        (a.out / "settling.json").write_text(json.dumps(findings, indent=2) + "\n")
        print(f"wrote {a.out / 'settling.json'}")
    finally:
        try:
            b.set_filter(original)  # also after a crash: a run that died left a channel on DC once
        finally:
            b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
