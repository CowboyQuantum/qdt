"""Probe 01 — OPX stream semantics and cadence. No device, no ADC: streams computed values.

Measures, per docs/probes/01-stream-semantics.md:
  1. delivery granularity (per point / per line / per frame) and partial-buffer visibility
  2. sustained points/s and inter-arrival statistics (the one quantitative output)
  3. positional addressing (value == loop index proves it)
  4. dtype/shape on fetch
  5. runtime variability without recompile (IO variable; input stream)

Each section is isolated so an API mismatch with your qm-qua version fails one section only.
Edit CONTROLLER_TYPE for your hardware generation.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

# ---- user-editable ---------------------------------------------------------------------------
CONTROLLER = "con1"
CONTROLLER_TYPE = "opx1"  # "opx1" for OPX+/OPX; "opx1000" with FEM config for OPX1000
N_OUTER = 64  # "lines" per frame
M_INNER = 256  # points per line
PACE_CYCLES = 100  # 4 ns units between points; 100 → ~2.5 Mpts/s producer-side ceiling
# ----------------------------------------------------------------------------------------------

CONFIG = {
    "version": 1,
    "controllers": {
        CONTROLLER: {
            "type": CONTROLLER_TYPE,
            "analog_outputs": {1: {"offset": 0.0}},
            "digital_outputs": {},
            "analog_inputs": {},
        }
    },
    "elements": {
        "dummy": {
            "singleInput": {"port": (CONTROLLER, 1)},
            "intermediate_frequency": 0,
            "operations": {},
        }
    },
    "pulses": {},
    "waveforms": {},
    "digital_waveforms": {},
}


def build_program(qua, variant: str):
    """variant: 'points' | 'lines' | 'frame' | 'io' | 'input_stream'."""
    with qua.program() as prog:
        i = qua.declare(int)
        j = qua.declare(int)
        v = qua.declare(int)
        n_inner = qua.declare(int, value=M_INNER)
        st = qua.declare_stream()
        if variant == "input_stream":
            n_in = qua.declare_input_stream(int, name="n_inner_in", size=1)
            qua.advance_input_stream(n_in)
            qua.assign(n_inner, n_in[0])
        if variant == "io":
            qua.assign(n_inner, qua.IO1)
        with qua.for_(i, 0, i < N_OUTER, i + 1):
            with qua.for_(j, 0, j < n_inner, j + 1):
                qua.assign(v, i * M_INNER + j)  # value == flat index → positional addressing check
                qua.save(v, st)
                qua.wait(PACE_CYCLES, "dummy")
        with qua.stream_processing():
            if variant in ("points", "io", "input_stream"):
                st.save_all("data")
            elif variant == "lines":
                st.buffer(M_INNER).save_all("data")
            elif variant == "frame":
                st.buffer(N_OUTER, M_INNER).save("data")
    return prog


def poll_handle(h, expected_total: int, timeout_s: float = 60.0):
    """Tight poll loop. Returns list of (t_wall, count_visible)."""
    log = []
    t0 = time.perf_counter()
    last = -1
    while True:
        try:
            n = h.count_so_far()
        except Exception:  # some versions: only is_processing + fetch_all
            n = len(h.fetch_all()) if not h.is_processing() else last
        t = time.perf_counter() - t0
        if n != last:
            log.append((t, n))
            last = n
        if (not h.is_processing() and n >= expected_total) or t > timeout_s:
            break
        time.sleep(0.0005)
    return log


def run_variant(qm, qua, variant: str, out: Path, findings: dict):
    prog = build_program(qua, variant)
    total_points = N_OUTER * M_INNER
    expected_items = {"points": total_points, "lines": N_OUTER, "frame": 1, "io": total_points, "input_stream": total_points}[variant]
    if variant == "io":
        qm.set_io1_value(M_INNER)
    job = qm.execute(prog)
    if variant == "input_stream":
        job.push_to_input_stream("n_inner_in", [M_INNER])
    h = job.result_handles.get("data")
    h.wait_for_values(1)
    log = poll_handle(h, expected_items)
    arr = h.fetch_all()
    if hasattr(arr, "dtype") and arr.dtype.names:  # structured array in some versions
        arr = arr["value"]
    # ---- derive findings
    import numpy as np

    arr = np.asarray(arr)
    inter = [b[0] - a[0] for a, b in zip(log, log[1:])]
    duration = log[-1][0] - log[0][0] if len(log) > 1 else float("nan")
    pts_per_item = total_points / expected_items
    f = {
        "variant": variant,
        "items_visible_steps": len(log),
        "first_visible_at_s": log[0][0] if log else None,
        "duration_s": duration,
        "sustained_points_per_s": (total_points / duration) if duration and duration > 0 else None,
        "inter_arrival_median_ms": 1e3 * statistics.median(inter) if inter else None,
        "inter_arrival_p95_ms": 1e3 * sorted(inter)[int(0.95 * (len(inter) - 1))] if inter else None,
        "fetch_dtype": str(arr.dtype),
        "fetch_shape": list(arr.shape),
        "partial_buffer_visible": (variant in ("lines", "frame")) and any(0 < n < expected_items for _, n in log),
        "positional_ok": bool(np.array_equal(arr.reshape(-1)[:total_points], np.arange(total_points))),
        "points_per_delivered_item": pts_per_item,
    }
    findings[variant] = f
    with (out / f"opx_{variant}_timing.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_wall_s", "items_visible"])
        w.writerows(log)
    print(json.dumps(f, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--cluster", default=None, help="cluster_name for QOP ≥ 2.x")
    ap.add_argument("--out", type=Path, default=Path("bench/fixtures/probe01"))
    ap.add_argument("--variants", default="points,lines,frame,io,input_stream")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from qm import QuantumMachinesManager, qua

    kw = {"host": args.host}
    if args.port:
        kw["port"] = args.port
    if args.cluster:
        kw["cluster_name"] = args.cluster
    qmm = QuantumMachinesManager(**kw)
    qm = qmm.open_qm(CONFIG)

    findings: dict = {}
    for variant in args.variants.split(","):
        print(f"\n=== variant: {variant} ===")
        try:
            run_variant(qm, qua, variant, args.out, findings)
        except Exception as e:  # isolate API mismatches per variant
            findings[variant] = {"variant": variant, "error": repr(e)}
            print(f"FAILED: {e!r}", file=sys.stderr)

    (args.out / "opx_findings.json").write_text(json.dumps(findings, indent=2))
    print("\n=== summary for docs/probes/01-stream-semantics.md ===")
    for v, f in findings.items():
        if "error" in f:
            print(f"{v:13s} ERROR {f['error']}")
            continue
        print(
            f"{v:13s} pts/s={f['sustained_points_per_s']:.3g}  "
            f"median={f['inter_arrival_median_ms']:.2f}ms p95={f['inter_arrival_p95_ms']:.2f}ms  "
            f"partial={f['partial_buffer_visible']} positional={f['positional_ok']} "
            f"dtype={f['fetch_dtype']} shape={f['fetch_shape']}"
        )
    print("Runtime-variable without recompile: io=%s input_stream=%s" % (
        "ok" if "error" not in findings.get("io", {"error": 1}) else "no",
        "ok" if "error" not in findings.get("input_stream", {"error": 1}) else "no",
    ))


if __name__ == "__main__":
    main()
