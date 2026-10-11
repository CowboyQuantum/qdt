"""Probe 01 — Keysight benchtop scope waveform transfer cadence (InfiniiVision-style SCPI).

Measures record length vs transfer time, sustained frames/s, and documents the explicit time axis.
Pull-based, whole-record source — the opposite of the OPX result stream.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resource", required=True, help='e.g. "TCPIP::192.168.0.10::INSTR" or "USB0::..."')
    ap.add_argument("--channel", type=int, default=1)
    ap.add_argument("--points", default="1000,10000,100000,1000000")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--out", type=Path, default=Path("bench/fixtures/probe01"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import pyvisa

    rm = pyvisa.ResourceManager()
    sc = rm.open_resource(args.resource)
    sc.timeout = 30000
    idn = sc.query("*IDN?").strip()
    print("IDN:", idn)
    sc.write(f":WAV:SOUR CHAN{args.channel}")
    sc.write(":WAV:FORM WORD")
    sc.write(":WAV:BYT LSBF")
    sc.write(":WAV:POIN:MODE RAW")

    rows, findings = [], {"idn": idn, "records": {}}
    for n in (int(x) for x in args.points.split(",")):
        sc.write(f":WAV:POIN {n}")
        times, lengths = [], []
        for _ in range(args.repeats):
            sc.write(":DIG")  # single acquisition; use :RUN + polling for continuous mode
            t0 = time.perf_counter()
            pre = sc.query(":WAV:PRE?").split(",")
            data = sc.query_binary_values(":WAV:DATA?", datatype="h", is_big_endian=False, container=list)
            dt = time.perf_counter() - t0
            times.append(dt)
            lengths.append(len(data))
        # preamble fields (InfiniiVision): format,type,points,count,xinc,xorig,xref,yinc,yorig,yref
        xinc, xorig = float(pre[4]), float(pre[5])
        med = sorted(times)[len(times) // 2]
        rec = {
            "requested_points": n,
            "returned_points": lengths[-1],
            "median_transfer_s": med,
            "sustained_frames_per_s": 1.0 / med,
            "sustained_points_per_s": lengths[-1] / med,
            "x_increment_s": xinc,
            "x_origin_s": xorig,
        }
        findings["records"][n] = rec
        rows += [(n, lengths[i], t) for i, t in enumerate(times)]
        print(json.dumps(rec))

    with (args.out / "scope_timing.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["requested_points", "returned_points", "transfer_s"])
        w.writerows(rows)
    (args.out / "scope_findings.json").write_text(json.dumps(findings, indent=2))
    print("\nScope: pull-based, whole record per query, explicit time axis from preamble (xorig + i*xinc).")


if __name__ == "__main__":
    main()
