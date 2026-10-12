"""Probe 01 — OPX1000 stream semantics and cadence (docs/probes/01-stream-semantics.md).

No device, no ADC: the programs stream computed values (value == flat loop index) from an LF-FEM, and the
only analog activity is an optional zero-amplitude pulse on one output (timestamp section). Sections:

  ladder       sustained delivery vs producer rate, per-line and per-point streaming, 10^3..10^6 pts/s
               and unpaced; poll + fetch cost; data loss                      -> spec items 1, 2
  granularity  per point / per line / whole frame at 10^5 pts/s; is a partial buffer visible or
               fetchable mid-acquisition?                                     -> spec item 1
  addressing   values == loop index (positional), dtype and shape on fetch    -> spec items 3, 4
  runtime      ONE compiled program run twice with different step count, sweep step (endpoint) and
               averaging count via input streams; IO1 via pause/resume        -> spec item 5
  timestamps   cadence with a timestamp stream attached vs without            -> spec item 3

Each section (and each run within it) is isolated: an API mismatch with your qm-qua/QOP version fails that
run only. Everything lands in --out as CSV/JSON; the summary at the end goes into the probe doc's Findings.
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import statistics
import sys
import time
import traceback
from pathlib import Path

import numpy as np

CONTROLLER = "con1"
POINTS_PER_LINE = 1000
DURATION_S = 5.0  # target length of each ladder run; long enough for a sustained-rate measurement
LADDER = [
    1e3,
    1e4,
    1e5,
    1e6,
    None,
]  # producer points/s; None = unpaced (as fast as the OPX loop runs)
GRANULARITY_RATE = 1e5
CLOCK_NS = 4  # QUA wait() unit


def make_config(fem: int, port: int) -> dict:
    """OPX1000 with one LF-FEM output. Only zero-amplitude pulses are ever played on it."""
    return {
        "version": 1,
        "controllers": {
            CONTROLLER: {
                "type": "opx1000",
                "fems": {fem: {"type": "LF", "analog_outputs": {port: {"offset": 0.0}}}},
            }
        },
        "elements": {
            "dummy": {
                "singleInput": {"port": (CONTROLLER, fem, port)},
                "intermediate_frequency": 0,
                "operations": {"zero": "zero_pulse"},
            }
        },
        "pulses": {
            "zero_pulse": {"operation": "control", "length": 16, "waveforms": {"single": "zero_wf"}}
        },
        "waveforms": {"zero_wf": {"type": "constant", "sample": 0.0}},
        "digital_waveforms": {},
    }


# ---- qm-qua version compatibility (the lab's version is only known on the day) ----------------------


def out_stream(qua):
    """declare_output_stream (qm-qua >= 1.2.4) or the older declare_stream."""
    return (getattr(qua, "declare_output_stream", None) or qua.declare_stream)()


def in_stream(qua, name: str, dtype, size: int = 1):
    """Client input stream: new signature (`"client", stream_id=...`) with fallback to the old one."""
    extra = (
        {"size": size} if size > 1 else {}
    )  # size=1 would declare a 1-element array, not a scalar
    try:
        return qua.declare_input_stream("client", stream_id=name, dtype=dtype, **extra)
    except TypeError:
        return qua.declare_input_stream(dtype, name=name, **extra)


# ---- programs ------------------------------------------------------------------------------------


def paced_program(
    qua, n_lines: int, m: int, rate: float | None, delivery: str, timestamps: bool = False
):
    """Outer n_lines x inner m loop saving value == flat index, one point per 1/rate seconds.

    delivery: 'points' (save_all per point) | 'lines' (buffer(m).save_all) | 'frame' (buffer(n,m).save)
    """
    wait_cycles = None if rate is None else max(4, round(1e9 / rate / CLOCK_NS))
    with qua.program() as prog:
        i = qua.declare(int)
        j = qua.declare(int)
        v = qua.declare(int)
        st = out_stream(qua)
        ts = out_stream(qua) if timestamps else None
        with qua.for_(i, 0, i < n_lines, i + 1):
            with qua.for_(j, 0, j < m, j + 1):
                qua.assign(v, i * m + j)
                qua.save(v, st)
                if timestamps:
                    qua.play("zero", "dummy", timestamp_stream=ts)
                if wait_cycles is not None:
                    qua.wait(wait_cycles, "dummy")
        with qua.stream_processing():
            if delivery == "points":
                st.save_all("data")
            elif delivery == "lines":
                st.buffer(m).save_all("data")
            else:
                st.buffer(n_lines, m).save("data")
            if timestamps:
                ts.save_all("ts")
    return prog


def runtime_program(qua):
    """Compiled once; step count, sweep step (so the endpoint) and averaging count arrive at run time.

    The step is an int input stream (sweep units of 1e-6): QOP 3.7.1 fails to compile a fixed-typed
    input stream (server "internal error"; see fixed_input_program).
    """
    with qua.program() as prog:
        params = in_stream(qua, "params", int, size=3)  # [n_steps, n_avg, step in 1e-6 units]
        j = qua.declare(int)
        k = qua.declare(int)
        x = qua.declare(int)
        acc = qua.declare(int)
        xs = out_stream(qua)
        accs = out_stream(qua)
        qua.advance_input_stream(params)
        with qua.for_(j, 0, j < params[0], j + 1):
            qua.assign(x, j * params[2])
            qua.assign(acc, 0)
            with qua.for_(k, 0, k < params[1], k + 1):
                qua.assign(acc, acc + 1)
            qua.save(x, xs)
            qua.save(acc, accs)
        with qua.stream_processing():
            xs.save_all("x")
            accs.save_all("acc")
    return prog


def fixed_input_program(qua):
    """Minimal fixed-typed input stream; records whether this QOP compiles one at all."""
    with qua.program() as prog:
        step = in_stream(qua, "step", qua.fixed)
        j = qua.declare(int)
        x = qua.declare(qua.fixed)
        st = out_stream(qua)
        qua.advance_input_stream(step)
        with qua.for_(j, 0, j < 10, j + 1):
            qua.assign(x, j * step)
            qua.save(x, st)
        with qua.stream_processing():
            st.save_all("x")
    return prog


def io_program(qua):
    """Step count read from IO1 after a pause, so the host can set it on a running job."""
    with qua.program() as prog:
        n = qua.declare(int)
        j = qua.declare(int)
        st = out_stream(qua)
        qua.pause()
        qua.assign(n, qua.IO1)
        with qua.for_(j, 0, j < n, j + 1):
            qua.save(j, st)
        with qua.stream_processing():
            st.save_all("data")
    return prog


# ---- version-tolerant helpers --------------------------------------------------------------------


def set_io1(qm, job, value: int) -> None:
    if hasattr(job, "set_io1_value"):  # QOP 3 / API v2 (OPX1000)
        job.set_io1_value(value)
    else:
        qm.set_io1_value(value)


def is_paused(job) -> bool:
    return bool(job.is_paused()) if hasattr(job, "is_paused") else False


def run_compiled(qm, program_id):
    if hasattr(qm, "add_to_queue"):  # API v2
        # add_to_queue returns while "In queue"; an input-stream push before "Running" fails
        job = qm.add_to_queue(program_id)
        job.wait_until("Running", timeout=30)
        return job
    return qm.queue.add_compiled(program_id).wait_for_execution()


def nonempty(shape_json: str) -> bool:
    """True if a logged fetch_all shape describes at least one value."""
    try:
        shape = json.loads(shape_json)
    except ValueError:
        return False
    return isinstance(shape, list) and int(np.prod(shape)) > 0


def flat(a) -> np.ndarray:
    a = np.asarray(a)
    if a.dtype.names:  # structured result in some versions
        a = a["value"]
    return a


# ---- measurement ---------------------------------------------------------------------------------


def watch(job, handle, expected_items: int, timeout_s: float, fetch_new: bool):
    """Poll from submission until done. Logs (t, items visible, fetch seconds, points fetched).

    fetch_new: fetch each newly visible slice, as a stream server would, and time it.
    """
    log, fetched, t0 = [], 0, time.perf_counter()
    last = -1
    while True:
        t = time.perf_counter() - t0
        n = handle.count_so_far()
        dt_fetch, got = 0.0, 0
        if fetch_new and n > fetched:
            f0 = time.perf_counter()
            chunk = flat(handle.fetch(slice(fetched, n)))
            dt_fetch = time.perf_counter() - f0
            got = int(chunk.size)
            fetched = n
        if n != last or got:
            log.append((t, n, dt_fetch, got))
            last = n
        if (not handle.is_processing() and n >= expected_items) or t > timeout_s:
            break
        time.sleep(0.0002)
    return log


def summarise(log, total_points: int, expected_items: int, wall_s: float, handle) -> dict:
    arrivals = [(t, n) for t, n, _, _ in log if n > 0]
    changes = [
        arrivals[k][0]
        for k in range(len(arrivals))
        if k == 0 or arrivals[k][1] != arrivals[k - 1][1]
    ]
    inter = [b - a for a, b in zip(changes, changes[1:])]
    first, last = (changes[0], changes[-1]) if changes else (float("nan"), float("nan"))
    points_per_item = total_points / expected_items
    first_points = arrivals[0][1] * points_per_item if arrivals else 0
    window = last - first
    fetch_s = sum(f for _, _, f, _ in log)
    fetched = sum(g for _, _, _, g in log)
    try:
        dataloss = bool(handle.has_dataloss())
    except Exception as e:
        dataloss = f"unknown ({e!r})"
    return {
        "items_expected": expected_items,
        "items_final": log[-1][1] if log else 0,
        "complete": bool(log) and log[-1][1] >= expected_items,
        "first_visible_s": first,
        "last_visible_s": last,
        "wall_s_incl_compile": wall_s,
        # points that arrived after the first visible batch, over the time they took (excludes compile/start)
        "delivered_points_per_s": (total_points - first_points) / window
        if window and window > 0
        else None,
        "visibility_steps": len(changes),
        "inter_arrival_median_ms": 1e3 * statistics.median(inter) if inter else None,
        "inter_arrival_p95_ms": 1e3 * sorted(inter)[int(0.95 * (len(inter) - 1))]
        if inter
        else None,
        "fetch_seconds_total": fetch_s,
        "fetch_us_per_point": 1e6 * fetch_s / fetched if fetched else None,
        "dataloss": dataloss,
    }


def write_log(path: Path, log) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_since_submit_s", "items_visible", "fetch_s", "points_fetched"])
        w.writerows(log)


def ladder_run(qm, qua, out: Path, delivery: str, rate: float | None) -> dict:
    m = POINTS_PER_LINE
    n_lines = max(10, round((rate or 2e6) * DURATION_S / m)) if rate else 2000
    total = n_lines * m
    expected = {"points": total, "lines": n_lines, "frame": 1}[delivery]
    prog = paced_program(qua, n_lines, m, rate, delivery)
    t0 = time.perf_counter()
    job = qm.execute(prog)
    handle = job.result_handles.get("data")
    log = watch(job, handle, expected, timeout_s=DURATION_S * 6 + 30, fetch_new=delivery != "frame")
    wall = time.perf_counter() - t0
    name = f"{delivery}_{'unpaced' if rate is None else f'{rate:.0e}'}"
    write_log(out / f"opx_{name}.csv", log)
    res = {"run": name, "delivery": delivery, "target_points_per_s": rate, "points": total}
    res |= summarise(log, total, expected, wall, handle)
    if delivery == "lines":  # addressing / dtype / shape on a complete fetch
        a = flat(handle.fetch_all())
        res["fetch_dtype"], res["fetch_shape"] = str(a.dtype), list(a.shape)
        res["positional_ok"] = bool(np.array_equal(a.reshape(-1)[:total], np.arange(total)))
    return res


def frame_partial_run(qm, qua, out: Path) -> dict:
    """Whole-frame buffer: does anything become visible or fetchable before the frame completes?"""
    m, rate = POINTS_PER_LINE, GRANULARITY_RATE
    n_lines = round(rate * DURATION_S / m)
    prog = paced_program(qua, n_lines, m, rate, "frame")
    job = qm.execute(prog)
    handle = job.result_handles.get("data")
    probes, t0 = [], time.perf_counter()
    # Poll until the frame is complete (count_so_far reaches 1), not until is_processing() drops:
    # on QOP 3.7.1 a fetch_all mid-frame returns None or raises "not a round number: <fill fraction>".
    while time.perf_counter() - t0 < DURATION_S * 6 + 30:
        t = time.perf_counter() - t0
        n = handle.count_so_far()
        try:
            a = handle.fetch_all()
            shape = None if a is None else list(np.shape(flat(a)))
        except Exception as e:
            shape = f"error {e!r}"
        probes.append((t, n, json.dumps(shape)))
        if n >= 1:
            break
        time.sleep(0.1)
    handle.wait_for_all_values()
    final = flat(handle.fetch_all())
    with (out / "opx_frame_midfetch.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_since_submit_s", "count_so_far", "fetch_all_shape"])
        w.writerows(probes)
    mid = [p for p in probes if p[1] in (0, None)]
    return {
        "run": "frame_partial",
        "mid_acquisition_polls": len(mid),
        "partial_visible": any(nonempty(p[2]) for p in mid),
        "partial_fetch_errors": [p[2] for p in mid if p[2].startswith('"error')][:3],
        "first_complete_s": probes[-1][0] if probes and probes[-1][1] >= 1 else None,
        "mid_fetch_samples": mid[-5:],
        "final_shape": list(final.shape),
        "positional_ok": bool(np.array_equal(final.reshape(-1), np.arange(n_lines * m))),
    }


def runtime_section(qm, qua) -> dict:
    res: dict = {}
    try:
        pid = qm.compile(runtime_program(qua))
        runs = []
        for n_steps, n_avg, step in [(50, 3, 1000), (120, 7, 2500)]:
            job = run_compiled(qm, pid)
            job.push_to_input_stream("params", [n_steps, n_avg, step])
            h = job.result_handles
            h.wait_for_all_values()
            x = flat(h.get("x").fetch_all())
            acc = flat(h.get("acc").fetch_all())
            runs.append(
                {
                    "pushed": {"n_steps": n_steps, "n_avg": n_avg, "step": step},
                    "got_n_steps": int(x.size),
                    "got_endpoint": int(x[-1]) if x.size else None,
                    "expected_endpoint": (n_steps - 1) * step,
                    "got_n_avg": sorted({int(a) for a in acc}),
                }
            )
        res["input_stream_same_compiled_program"] = runs
        res["input_stream_ok"] = all(
            r["got_n_steps"] == r["pushed"]["n_steps"]
            and r["got_endpoint"] == r["expected_endpoint"]
            and r["got_n_avg"] == [r["pushed"]["n_avg"]]
            for r in runs
        )
    except Exception:
        res["input_stream_error"] = traceback.format_exc(limit=3)
    try:
        qm.compile(fixed_input_program(qua))
        res["fixed_input_stream_compiles"] = True
    except Exception as e:
        res["fixed_input_stream_compiles"] = f"no: {type(e).__name__}: {str(e)[:200]}"
    try:
        got = []
        for n in (40, 90):
            job = qm.execute(io_program(qua))
            t0 = time.perf_counter()
            while not is_paused(job) and time.perf_counter() - t0 < 10:
                time.sleep(0.01)
            set_io1(qm, job, n)
            job.resume()
            h = job.result_handles
            h.wait_for_all_values()
            got.append((n, int(flat(h.get("data").fetch_all()).size)))
        res["io1_runs"] = got
        res["io1_ok"] = all(a == b for a, b in got)
    except Exception:
        res["io1_error"] = traceback.format_exc(limit=3)
    return res


def timestamp_section(qm, qua, out: Path) -> dict:
    m, rate = POINTS_PER_LINE, GRANULARITY_RATE
    n_lines = round(rate * DURATION_S / m)
    total = n_lines * m
    prog = paced_program(qua, n_lines, m, rate, "lines", timestamps=True)
    t0 = time.perf_counter()
    job = qm.execute(prog)
    h = job.result_handles.get("data")
    log = watch(job, h, n_lines, timeout_s=DURATION_S * 6 + 30, fetch_new=True)
    res = {"run": "lines_1e+05_with_timestamps"} | summarise(
        log, total, n_lines, time.perf_counter() - t0, h
    )
    ts = flat(job.result_handles.get("ts").fetch_all())
    res["timestamps"] = int(ts.size)
    res["timestamp_dtype"] = str(ts.dtype)
    if ts.size > 1:
        d = np.diff(ts.astype(np.int64))
        res["timestamp_step_median"] = float(np.median(d))  # clock cycles (4 ns) between points
    write_log(out / "opx_lines_1e+05_timestamps.csv", log)
    return res


def offline_check(fem: int, ao: int) -> None:
    from qm import QuantumMachinesManager, generate_qua_script, qua

    try:  # lets generate_qua_script validate the config too (normally learned from the server)
        QuantumMachinesManager.set_capabilities_offline()
    except Exception as e:
        print(f"note: config not fully validated offline ({e!r})")
    config = make_config(fem, ao)
    programs = {
        **{
            f"{d}_{r}": paced_program(qua, 10, 100, r, d)
            for d in ("points", "lines", "frame")
            for r in (1e5, None)
        },
        "lines_timestamps": paced_program(qua, 10, 100, 1e5, "lines", timestamps=True),
        "runtime": runtime_program(qua),
        "fixed_input": fixed_input_program(qua),
        "io": io_program(qua),
    }
    for name, prog in programs.items():
        generate_qua_script(prog, config)
        print(f"ok  {name}")
    print(f"offline check passed with qm-qua {importlib.metadata.version('qm-qua')}")


# ---- main ----------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--host", help="OPX1000 / cluster gateway address")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--cluster", default=None, help="cluster_name (QOP 2.x and later)")
    ap.add_argument("--fem", type=int, default=1, help="slot number of an LF-FEM")
    ap.add_argument(
        "--ao", type=int, default=1, help="LF-FEM analog output used for waits/zero pulses"
    )
    ap.add_argument("--out", type=Path, default=Path("bench/fixtures/probe01"))
    ap.add_argument("--sections", default="ladder,granularity,runtime,timestamps")
    ap.add_argument(
        "--quick", action="store_true", help="1 s runs, 10^4/10^5 only — a dry run of the plumbing"
    )
    ap.add_argument(
        "--offline-check",
        action="store_true",
        help="no OPX needed: build every program and serialise it with the config (catches API mismatches)",
    )
    args = ap.parse_args()
    if args.offline_check:
        offline_check(args.fem, args.ao)
        return
    if not args.host:
        ap.error("--host is required unless --offline-check")
    args.out.mkdir(parents=True, exist_ok=True)

    global DURATION_S, LADDER
    if args.quick:
        DURATION_S, LADDER = 1.0, [1e4, 1e5]

    from qm import QuantumMachinesManager, qua

    kw = {"host": args.host}
    if args.port:
        kw["port"] = args.port
    if args.cluster:
        kw["cluster_name"] = args.cluster
    qmm = QuantumMachinesManager(**kw)
    env = {"qm_qua": importlib.metadata.version("qm-qua"), "python": sys.version.split()[0]}
    try:
        env["server"] = str(qmm.version())
    except Exception as e:
        env["server"] = f"unknown ({e!r})"
    print("environment:", json.dumps(env))
    qm = qmm.open_qm(make_config(args.fem, args.ao), close_other_machines=True)

    findings: dict = {
        "environment": env,
        "fem": args.fem,
        "ao": args.ao,
        "quick": args.quick,
        "runs": [],
    }
    sections = args.sections.split(",")

    def attempt(label, fn):
        print(f"\n=== {label} ===", flush=True)
        try:
            r = fn()
        except Exception:
            r = {"run": label, "error": traceback.format_exc(limit=3)}
            print(r["error"], file=sys.stderr)
        print(json.dumps(r, indent=2, default=str), flush=True)
        return r

    if "ladder" in sections:
        for delivery in ("lines", "points"):
            for rate in LADDER:
                findings["runs"].append(
                    attempt(
                        f"ladder {delivery} {rate}",
                        lambda d=delivery, r=rate: ladder_run(qm, qua, args.out, d, r),
                    )
                )
    if "granularity" in sections:
        findings["frame_partial"] = attempt(
            "granularity: whole frame", lambda: frame_partial_run(qm, qua, args.out)
        )
    if "runtime" in sections:
        findings["runtime"] = attempt("runtime parameters", lambda: runtime_section(qm, qua))
    if "timestamps" in sections:
        findings["timestamps"] = attempt("timestamps", lambda: timestamp_section(qm, qua, args.out))

    (args.out / "opx_findings.json").write_text(json.dumps(findings, indent=2, default=str))
    qm.close()

    print("\n=== summary for docs/probes/01-stream-semantics.md ===")
    print(f"qm-qua {env['qm_qua']}, server {env['server']}")
    for r in findings["runs"]:
        if "error" in r:
            print(f"{r['run']:22s} ERROR (see opx_findings.json)")
            continue
        dpps = r["delivered_points_per_s"]
        print(
            f"{r['run']:22s} delivered {dpps:,.0f} pts/s"
            if dpps
            else f"{r['run']:22s} delivered n/a",
            f"| median {r['inter_arrival_median_ms']} ms p95 {r['inter_arrival_p95_ms']} ms",
            f"| fetch {r['fetch_us_per_point']} us/pt | dataloss {r['dataloss']} | complete {r['complete']}",
        )
    fp = findings.get("frame_partial", {})
    print("whole frame partial visible:", fp.get("partial_visible", fp.get("error", "n/a")))
    if fp.get("partial_fetch_errors"):
        print("  mid-frame fetch_all errors:", fp["partial_fetch_errors"][0])
    rt = findings.get("runtime", {})
    print(
        "runtime via input stream (same compiled program):",
        rt.get("input_stream_ok", rt.get("input_stream_error")),
    )
    print("fixed-typed input stream compiles:", rt.get("fixed_input_stream_compiles"))
    print("runtime via IO1:", rt.get("io1_ok", rt.get("io1_error")))
    ts = findings.get("timestamps", {})
    print(
        "timestamps: delivered",
        ts.get("delivered_points_per_s"),
        "pts/s; step",
        ts.get("timestamp_step_median"),
        "clock cycles (4 ns)",
    )
    print(f"\nall outputs in {args.out}")


if __name__ == "__main__":
    main()
