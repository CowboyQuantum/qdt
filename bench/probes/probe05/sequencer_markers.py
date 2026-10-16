"""Probe 05 — the sequencer's marker lines (docs/probes/05-sequencer-trigger-lines.md).

Three numbers the drivers now assume and two counts that must be exact, measured with the OPX's
digital outputs wired to the scope's EXT TRIG input and to the QDAC-II's external trigger input:

1. **marker**: the marker's high level into the scope input (sets `trigger_level_v`), its width, and
   the delay from the marker's edge to the analog edge played in the same shot (the offset between a
   record's t = 0 and the op the capture sits at; ADR 0063).
2. **pacing**: how many records the scope delivers for N markers played s apart, through the driver's
   per-record `:DIGitize`, for several s; and whether the scope accepts segmented acquisition. The
   smallest s with N records is the floor a shot capture's sequence must pace itself to.
3. **qdac**: a 5-point staircase loaded on a QDAC-II channel (`QDac2.load`, `trigger_in` = ext1) and
   advanced by 5 markers on do2: steps counted against markers, the trigger-to-output latency and the
   settle of each step (Probe 04's metrics), and whether `init` already moved the output before the
   first marker (ADR 0064).

Wiring (all BNC):
    OPX LF-FEM ao1 → scope ch1, 50 Ω          (the analog edge)
    OPX do1        → scope EXT TRIG IN         (the scope's trigger line)
    OPX do3        → scope ch3, 1 MΩ           (marker section: a copy of the marker, level and width)
    OPX do2        → QDAC-II ext1 (rear)       (qdac section: the DAC's trigger line)
    QDAC ch01      → scope ch2, 1 MΩ           (qdac section: the staircase; --qdac-scope-channel)

The OPX is driven through the driver's own config (`Opx1000.config()` with the two lines), so the
elements, the marker pulse and `MARKER_NS` are the ones a sweep will use. The scope is driven through
the driver for the pacing section (external trigger at arm, `_ScopeRecordSource` per record) and
through its transport for the single-shot records of the other sections, as Probe 04 did.

    uv run python bench/probes/probe05/sequencer_markers.py --opx <qm-host> \\
        --scope "TCPIP::<scope>::5025::SOCKET" --qdac "ASRL/dev/cu.usbserial-NNNN::INSTR" \\
        [--fem 1] [--sections marker,pacing,qdac] [--qdac-channel 1] [--qdac-scope-channel 2] \\
        [--out bench/fixtures/probe05]
"""

import argparse
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.stand import ChannelMap, InstrumentConfig

STEP_V = 0.25
STEP_NS = 2000
MARKER_REPEATS = 5
MARKER_WINDOW_S = 4e-6
MARKER_SPACING_S = 0.01
PACING_RECORDS = 10
PACING_SPACINGS_S = (0.5, 0.2, 0.1, 0.05, 0.02)
PACING_WINDOW_S = 1e-3
PACING_TIMEOUT_S = 15.0
QDAC_LEVELS = (0.0, 0.25, 0.5, 0.75, 1.0)
QDAC_SPACING_S = 0.1
TRIGGER_TIMEOUT_S = 5.0
POINTS = 4000


class Bench:
    def __init__(self, a):
        from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX
        from qdt_lab.drivers.qm.opx1000 import Opx1000

        self.a = a
        self.opx = Opx1000.from_config(
            InstrumentConfig(
                id="opx",
                backend="qua",
                capabilities=("sequencer",),
                settings={"address": a.opx, "fem": a.fem, "output_mode": "direct"},
            ),
            (
                ChannelMap(logical="P2_pulse", instrument="opx", channel="ao1", quantity="voltage"),
                ChannelMap(
                    logical="scope_trigger", instrument="opx", channel="do1", quantity="voltage"
                ),
                ChannelMap(
                    logical="dac_trigger", instrument="opx", channel="do2", quantity="voltage"
                ),
                ChannelMap(
                    logical="marker_copy", instrument="opx", channel="do3", quantity="voltage"
                ),
            ),
        )
        self.scope_inst = InstrumentConfig(
            id="scope0",
            backend="infiniivision",
            capabilities=("waveform_sense",),
            settings={"address": a.scope},
        )
        self.scope_channels = tuple(
            ChannelMap(logical=f"ch{n}", instrument="scope0", channel=str(n), quantity="voltage")
            for n in (1, 2, 3, 4)
        )
        # a `:DIGitize` left waiting by an earlier session blocks the scope's `*OPC?` until a trigger
        # arrives: fire a few markers before the first query that waits on it
        self.execute(self.program_markers(5, 0.05, ("do1", "do3"), step=False)).halt()
        self.scope = InfiniiVisionX.from_config(self.scope_inst, self.scope_channels)
        self._s = self.scope._t
        self._s._r.timeout = 20000
        self.qdac = None

    # --- OPX programs through the driver's config -------------------------------------------------

    def qm(self):
        return self.opx._ensure()

    def program_markers(self, n: int | None, spacing_s: float, lines: tuple[str, ...], step: bool):
        """`n` repeats (None: endless), `spacing_s` apart: a marker on each of `lines` and, with
        `step`, a 2 µs step of STEP_V on ao1 at the same moment (every element aligned first)."""
        from qm import qua

        from qdt_lab.drivers.qm.opx1000 import CLOCK_NS, _element, _trigger_element

        a_ref = self.opx.amplitude_ref
        spacing = max(4, round(spacing_s * 1e9 / CLOCK_NS))
        with qua.program() as prog:
            k = qua.declare(int)
            loop = qua.infinite_loop_() if n is None else qua.for_(k, 0, k < n, k + 1)
            with loop:
                qua.align()
                for line in lines:
                    qua.play("marker", _trigger_element(line))
                if step:
                    qua.play(
                        "const" * qua.amp(STEP_V / a_ref),
                        _element("ao1"),
                        duration=STEP_NS // CLOCK_NS,
                    )
                    qua.ramp_to_zero(_element("ao1"), 1)
                qua.wait(spacing)
        return prog

    def program_staircase(self, n: int, spacing_s: float):
        """One marker on do1 (the scope's trigger), then `n` markers on do2 `spacing_s` apart."""
        from qm import qua

        from qdt_lab.drivers.qm.opx1000 import CLOCK_NS, _trigger_element

        spacing = max(4, round(spacing_s * 1e9 / CLOCK_NS))
        with qua.program() as prog:
            k = qua.declare(int)
            qua.play("marker", _trigger_element("do1"))
            qua.wait(spacing)
            with qua.for_(k, 0, k < n, k + 1):
                qua.play("marker", _trigger_element("do2"))
                qua.wait(spacing)
        return prog

    def execute(self, prog):
        return self.qm().execute(prog)

    # --- scope front panel and single-shot records (as Probe 04) -----------------------------------

    def front_panel(
        self, channels: dict[int, tuple[float, float]], window_s: float, ext_level_v: float
    ):
        """`channels`: number -> (volts/div, offset); every listed input DC, 1 MΩ unless `fifty`."""
        w = self._s.write
        w(":STOP")
        for n, (scale, offset) in channels.items():
            impedance = "FIFTy" if n == 1 else "ONEMeg"
            for c in (
                f":CHANnel{n}:DISPlay 1",
                f":CHANnel{n}:COUPling DC",
                f":CHANnel{n}:IMPedance {impedance}",
                f":CHANnel{n}:PROBe 1",
                f":CHANnel{n}:SCALe {scale:.6g}",
                f":CHANnel{n}:OFFSet {offset:.6g}",
            ):
                w(c)
        for c in (
            ":TIMebase:REFerence LEFT",
            f":TIMebase:RANGe {window_s:.9g}",
            f":TIMebase:POSition {-window_s / 10:.9g}",
            ":TRIGger:MODE EDGE",
            ":TRIGger:EDGE:SOURce EXTernal",
            ":TRIGger:EDGE:SLOPe POSitive",
            ":TRIGger:EDGE:COUPling DC",
            f":TRIGger:EDGE:LEVel {ext_level_v:.6g}",
            ":TRIGger:SWEep NORMal",
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
        self._s.query(":AER?")
        self._s.query(":TER?")
        self._s.write(":SINGle")
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < TRIGGER_TIMEOUT_S:
            if int(float(self._s.query(":AER?"))) == 1:
                return
            time.sleep(0.005)
        raise TimeoutError("the scope did not arm")

    def wait_trigger(self) -> bool:
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < TRIGGER_TIMEOUT_S:
            if int(float(self._s.query(":TER?"))) == 1:
                return True
            time.sleep(0.005)
        return False

    def read(self, channel: int) -> tuple[np.ndarray, np.ndarray]:
        self._s.write(f":WAVeform:SOURce CHANnel{channel}")
        self._s.query("*OPC?")
        pre = [p.strip() for p in self._s.query(":WAVeform:PREamble?").split(",")]
        xinc, xorig, xref = float(pre[4]), float(pre[5]), float(pre[6])
        yinc, yorig, yref = float(pre[7]), float(pre[8]), float(pre[9])
        codes = self._s.query_block(":WAVeform:DATA?", "<i2")
        t = (np.arange(codes.size) - xref) * xinc + xorig
        return t, (codes.astype(np.float64) - yref) * yinc + yorig

    def restore(self) -> None:
        self._s.write(":TRIGger:EDGE:SOURce CHANnel1")
        self._s.write(":TRIGger:SWEep AUTO")
        self._s.write(":RUN")

    def close(self) -> None:
        try:
            self.restore()
        finally:
            self.scope.close()
            self.opx.close()
            if self.qdac is not None:
                self.qdac.close()


class _Drain:
    """Reads a source's frames on a thread from the moment it is made, as the executor does."""

    def __init__(self, source) -> None:
        self.got: list = []
        self.error: Exception | None = None

        def run() -> None:
            try:
                self.got.extend(source.frames())
            except Exception as e:  # reported as where the count ended
                self.error = e

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()


def edges(t: np.ndarray, y: np.ndarray, level: float, rising: bool = True) -> np.ndarray:
    """Times where `y` crosses `level` upward (or downward)."""
    above = y > level
    k = (
        np.flatnonzero(above[1:] & ~above[:-1])
        if rising
        else np.flatnonzero(~above[1:] & above[:-1])
    )
    return t[k + 1]


def section_marker(b: Bench, a, findings: dict) -> None:
    """Level and width of the marker (do3's copy on ch3), delay from the EXT trigger (do1) to the
    analog edge on ch1."""
    rows = []
    # the first pass finds the marker's level with a generous EXT level; later passes use half of it
    ext_level = 0.5
    for k in range(MARKER_REPEATS):
        b.front_panel({1: (0.1, 0.1), 3: (1.0, 1.5)}, MARKER_WINDOW_S, ext_level)
        b.arm_single()
        job = b.execute(b.program_markers(1, MARKER_SPACING_S, ("do1", "do3"), step=True))
        if not b.wait_trigger():
            print(f"  rep {k}: no trigger on EXT")
            job.halt()
            continue
        t1, y1 = b.read(1)
        t2, y2 = b.read(3)
        high = float(np.percentile(y2, 95))
        low = float(np.percentile(y2, 5))
        half = (high + low) / 2
        up, down = edges(t2, y2, half), edges(t2, y2, half, rising=False)
        width = float(down[0] - up[0]) if up.size and down.size else float("nan")
        a_edge = edges(t1, y1, STEP_V / 2)
        row = {
            "marker_high_v": high,
            "marker_low_v": low,
            "marker_width_s": width,
            "marker_edge_s": float(up[0]) if up.size else float("nan"),
            "analog_edge_s": float(a_edge[0]) if a_edge.size else float("nan"),
            "analog_plateau_v": float(np.percentile(y1, 95)),
        }
        row["marker_to_analog_s"] = row["analog_edge_s"] - row["marker_edge_s"]
        rows.append(row)
        ext_level = half
        np.savez_compressed(a.out / f"marker_{k}.npz", t1=t1, y1=y1, t2=t2, y2=y2)
        print(
            f"  rep {k}: marker {high:.2f} V high, {width * 1e9:.0f} ns wide, edge at {row['marker_edge_s'] * 1e9:+.0f} ns "
            f"from EXT; analog edge at {row['analog_edge_s'] * 1e9:+.0f} ns ({row['marker_to_analog_s'] * 1e9:+.0f} ns after the marker)"
        )
        job.halt()
    if rows:
        med = {k: float(np.nanmedian([r[k] for r in rows])) for k in rows[0]}
        med["repeats"] = len(rows)
        findings["marker"] = med
        print(
            f"  → marker {med['marker_high_v']:.2f} V into 1 MΩ, {med['marker_width_s'] * 1e9:.0f} ns; the analog edge "
            f"follows the marker by {med['marker_to_analog_s'] * 1e9:.0f} ns (EXT-triggered record: t = 0 is the marker)"
        )


def section_pacing(b: Bench, a, findings: dict) -> None:
    """Records per second through the driver (EXT trigger at arm, one `:DIGitize` per record) under
    an endless marker train at each spacing: the time per record is max(spacing, the scope's re-arm),
    so the smallest spacing whose records come one per marker is the floor. Then whether segmented
    acquisition is accepted."""
    from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX

    level = findings.get("marker", {}).get("marker_high_v", 2.0) / 2
    b.front_panel({1: (0.1, 0.1)}, PACING_WINDOW_S, level)
    scope = InfiniiVisionX(b._s, b.scope_channels, external_trigger_level_v=level)
    ds = Dataset(
        dataset_id="pacing",
        name="pacing",
        dims=(Dimension(name="record", size=PACING_RECORDS), Dimension(name="time", size=200)),
        coords=(
            LinearCoordinate(
                name="time", dim="time", unit="s", start=0.0, stop=PACING_WINDOW_S * 0.9, num=200
            ),
        ),
        data_vars=(DataVariable(name="v", dims=("record", "time"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="live", label="probe05"),
        created_at=datetime.now(UTC),
    )
    results = []
    for spacing in PACING_SPACINGS_S:
        job = b.execute(b.program_markers(None, spacing, ("do1",), step=True))
        time.sleep(0.5)
        stamps: list[float] = []
        t0 = time.perf_counter()
        error = None
        try:
            for _ in scope.arm("ch1", ds, "v").frames():
                stamps.append(time.perf_counter() - t0)
        except Exception as e:  # the count ends where the scope stopped answering
            error = str(e)[:120]
        job.halt()
        gaps = np.diff(stamps) if len(stamps) > 1 else np.array([])
        row = {
            "spacing_s": spacing,
            "records": len(stamps),
            "elapsed_s": stamps[-1] if stamps else None,
            "s_per_record_median": float(np.median(gaps)) if gaps.size else None,
            "markers_per_record_median": float(np.median(gaps) / spacing) if gaps.size else None,
            "error": error,
        }
        results.append(row)
        print(
            f"  {spacing * 1e3:5.0f} ms apart: {len(stamps)}/{PACING_RECORDS} records, "
            + (
                f"{row['s_per_record_median'] * 1e3:.0f} ms per record = {row['markers_per_record_median']:.1f} markers"
                if gaps.size
                else "no gaps"
            )
            + (f" ({error})" if error else "")
        )
        time.sleep(0.5)
    b._s.write(":STOP")
    b._s.write(":ACQuire:MODE SEGMented")
    b._s.write(f":ACQuire:SEGMented:COUNt {PACING_RECORDS}")
    mode = b._s.query(":ACQuire:MODE?").strip()
    err = b._s.query(":SYSTem:ERRor?").strip()
    b._s.write(":ACQuire:MODE RTIMe")
    rearm = [r["s_per_record_median"] for r in results if r["s_per_record_median"]]
    findings["pacing"] = {
        "rows": results,
        "segmented_mode_readback": mode,
        "segmented_error": err,
        "rearm_s": float(min(rearm)) if rearm else None,
        "floor_s": min(
            (
                r["spacing_s"]
                for r in results
                if r["markers_per_record_median"] and r["markers_per_record_median"] < 1.5
            ),
            default=None,
        ),
    }
    print(
        f"  → re-arm about {findings['pacing']['rearm_s']} s per record; one record per marker down to "
        f"{findings['pacing']['floor_s']} s; segmented: mode reads {mode!r}, error {err!r}"
    )


def section_qdac(b: Bench, a, findings: dict) -> None:
    """A staircase on the QDAC advanced by markers on do2 into its ext input; the scope (EXT on do1)
    records ch3 over the whole staircase."""
    from qdt_lab.drivers.qdevil.qdac2 import QDac2

    b.qdac = QDac2.from_config(
        InstrumentConfig(
            id="dac0",
            backend="qdac2",
            capabilities=("level_source", "triggered_level_source"),
            settings={"address": a.qdac, "trigger_in": a.qdac_trigger},
        ),
        (),
    )
    ch = f"ch{a.qdac_channel:02d}"
    sc = a.qdac_scope_channel
    level = findings.get("marker", {}).get("marker_high_v", 2.0) / 2
    n = len(QDAC_LEVELS)
    window = (n + 1.5) * QDAC_SPACING_S
    rows = []
    for k in range(3):
        b.qdac.set(ch, -0.25)  # a level no list point has: a move before the first marker shows
        time.sleep(0.1)
        b.front_panel({sc: (0.25, 0.4)}, window, level)
        b.qdac.load(ch, QDAC_LEVELS)
        b.arm_single()
        job = b.execute(b.program_staircase(n, QDAC_SPACING_S))
        if not b.wait_trigger():
            print(f"  rep {k}: no trigger on EXT")
            job.halt()
            b.qdac.release(ch)
            continue
        t, y = b.read(sc)
        job.halt()
        b.qdac.release(ch)
        np.savez_compressed(a.out / f"staircase_{k}.npz", t=t, y=y)
        # expected marker times: the do2 markers come QDAC_SPACING_S after the do1 marker (t = 0)
        marker_times = QDAC_SPACING_S * (1 + np.arange(n))
        before = float(np.mean(y[(t > 0.01) & (t < QDAC_SPACING_S - 0.01)]))
        step_edges = []
        for i, v in enumerate(QDAC_LEVELS):
            prev = QDAC_LEVELS[i - 1] if i else before
            mid = (prev + v) / 2
            sel = (t > marker_times[i] - 0.02) & (t < marker_times[i] + QDAC_SPACING_S - 0.02)
            e = edges(t[sel], y[sel], mid, rising=v > prev)
            step_edges.append(float(e[0]) if e.size else float("nan"))
        latencies = np.array(step_edges) - marker_times
        settle = []
        for i, v in enumerate(QDAC_LEVELS):
            sel = (t > marker_times[i]) & (t < marker_times[i] + QDAC_SPACING_S - 0.01)
            tt, yy = t[sel], y[sel]
            final = float(np.mean(yy[-max(5, yy.size // 10) :]))
            tol = max(0.01 * abs(v - (QDAC_LEVELS[i - 1] if i else before)), 2e-3)
            outside = np.flatnonzero(np.abs(yy - final) > tol)
            settle.append(
                float(tt[outside[-1] + 1] - marker_times[i])
                if outside.size and outside[-1] + 1 < tt.size
                else 0.0
            )
        row = {
            "level_before_first_marker_v": before,
            "moved_at_init": abs(before - (-0.25)) > 0.05,
            "steps_found": int(np.isfinite(latencies).sum()),
            "latency_s": [float(x) for x in latencies],
            "settle_1pct_s": settle,
            "final_levels_v": [
                float(
                    np.mean(
                        y[
                            (t > marker_times[i] + 0.05)
                            & (t < marker_times[i] + QDAC_SPACING_S - 0.01)
                        ]
                    )
                )
                for i in range(n)
            ],
        }
        rows.append(row)
        print(
            f"  rep {k}: {row['steps_found']}/{n} steps; latency "
            + ", ".join(f"{x * 1e3:.2f}" for x in latencies)
            + " ms; moved at init: "
            + str(row["moved_at_init"])
        )
    if rows:
        findings["qdac"] = {
            "trigger_in": a.qdac_trigger,
            "levels_v": list(QDAC_LEVELS),
            "spacing_s": QDAC_SPACING_S,
            "repeats": rows,
            "latency_s_median": float(np.nanmedian(np.concatenate([r["latency_s"] for r in rows]))),
            "steps_per_markers": [f"{r['steps_found']}/{n}" for r in rows],
            "moved_at_init": any(r["moved_at_init"] for r in rows),
        }
        print(
            f"  → {findings['qdac']['steps_per_markers']} steps per {n} markers; trigger-to-output "
            f"{findings['qdac']['latency_s_median'] * 1e3:.2f} ms; moved at init: {findings['qdac']['moved_at_init']}"
        )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--opx", required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--qdac")
    p.add_argument("--fem", type=int, default=1)
    p.add_argument("--qdac-channel", type=int, default=1)
    p.add_argument("--qdac-trigger", default="ext1")
    p.add_argument("--qdac-scope-channel", type=int, default=2)
    p.add_argument("--sections", default="marker,pacing,qdac")
    p.add_argument("--out", type=Path, default=Path("bench/fixtures/probe05"))
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    wanted = {s.strip() for s in a.sections.split(",")}
    if "qdac" in wanted and not a.qdac:
        p.error("--qdac is needed for the qdac section")
    b = Bench(a)
    findings: dict = {"fem": a.fem}
    existing = a.out / "markers.json"
    if existing.exists():  # sections run one at a time merge into one file
        findings.update(json.loads(existing.read_text()))
    findings["run_at"] = datetime.now(UTC).isoformat()
    try:
        if "marker" in wanted:
            print("marker")
            section_marker(b, a, findings)
        if "pacing" in wanted:
            print("pacing")
            section_pacing(b, a, findings)
        if "qdac" in wanted:
            print("qdac")
            section_qdac(b, a, findings)
        (a.out / "markers.json").write_text(json.dumps(findings, indent=2) + "\n")
        print(f"wrote {a.out / 'markers.json'}")
    finally:
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
