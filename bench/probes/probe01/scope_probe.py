"""Probe 01 — Keysight HD304MSO waveform transfer (docs/probes/01-stream-semantics.md, scope column).

Pull-based, whole-record source with an explicit time axis — the opposite of the OPX on every count.
Measures, per requested record length:
  - acquisition time (:DIGitize until *OPC) and transfer time (:WAV:PRE? + :WAV:DATA?) separately
  - sustained frames/s and points/s for acquire + transfer
  - the time axis from the preamble of EVERY capture: does x_origin move between captures? That decides
    whether the Dataset contract needs a per-record time axis (ADR 0009, open freeze question).

No signal needs to be connected: the trigger is set to AUTO so captures complete on noise. The script uses the
InfiniiVision-family SCPI the HD3 series shares; every setup command is followed by an error-queue check, so a
command your firmware does not accept is reported rather than silently ignored.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

# preamble fields (InfiniiVision family): format,type,points,count,xinc,xorig,xref,yinc,yorig,yref
PRE = ["format", "type", "points", "count", "xinc", "xorig", "xref", "yinc", "yorig", "yref"]


def check_errors(sc, after: str, errors: list) -> None:
    for _ in range(10):
        e = sc.query(":SYSTem:ERRor?").strip()
        if e.startswith(("+0", "0")):
            return
        errors.append(f"after {after!r}: {e}")
        print(f"instrument error after {after!r}: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--resource",
        required=True,
        help='VISA resource, e.g. "TCPIP::192.168.0.10::INSTR" or "USB0::..."',
    )
    ap.add_argument("--channel", type=int, default=1)
    ap.add_argument(
        "--points", default="1000,10000,100000,1000000", help="requested record lengths"
    )
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path("bench/fixtures/probe01"))
    ap.add_argument(
        "--backend", default="", help='pyvisa backend; "" = vendor VISA if present, else "@py"'
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import pyvisa

    try:  # vendor VISA (Keysight IO Libraries / NI-VISA) if installed, else the pure-Python backend
        rm = pyvisa.ResourceManager(args.backend) if args.backend else pyvisa.ResourceManager()
    except (OSError, ValueError):
        rm = pyvisa.ResourceManager("@py")
    print("VISA backend:", rm)
    sc = rm.open_resource(args.resource)
    sc.timeout = 30000
    sc.read_termination = "\n"
    sc.write_termination = "\n"
    errors: list[str] = []
    idn = sc.query("*IDN?").strip()
    print("IDN:", idn)
    sc.write("*CLS")
    for cmd in [
        ":TRIGger:SWEep AUTO",  # complete captures without a signal
        f":CHANnel{args.channel}:DISPlay ON",
        f":WAVeform:SOURce CHANnel{args.channel}",
        ":WAVeform:FORMat WORD",  # 14-bit ADC: WORD keeps full resolution
        ":WAVeform:BYTeorder LSBFirst",
        ":WAVeform:POINts:MODE RAW",
    ]:
        sc.write(cmd)
        check_errors(sc, cmd, errors)
    unsigned = sc.query(":WAVeform:UNSigned?").strip() in ("1", "ON")
    datatype = "H" if unsigned else "h"

    findings: dict = {"idn": idn, "unsigned": unsigned, "records": {}, "errors": errors}
    rows = []
    for n in (int(x) for x in args.points.split(",")):
        sc.write(f":WAVeform:POINts {n}")
        check_errors(sc, f":WAVeform:POINts {n}", errors)
        acq, xfer, lengths, xorigs, xincs = [], [], [], [], []
        for k in range(args.repeats):
            t0 = time.perf_counter()
            sc.write(":DIGitize")
            sc.query("*OPC?")  # blocks until the acquisition completes
            t1 = time.perf_counter()
            pre = dict(zip(PRE, sc.query(":WAVeform:PREamble?").split(",")))
            data = sc.query_binary_values(
                ":WAVeform:DATA?", datatype=datatype, is_big_endian=False, container=list
            )
            t2 = time.perf_counter()
            acq.append(t1 - t0)
            xfer.append(t2 - t1)
            lengths.append(len(data))
            xorigs.append(float(pre["xorig"]))
            xincs.append(float(pre["xinc"]))
            rows.append(
                (n, k, len(data), t1 - t0, t2 - t1, pre["xorig"], pre["xinc"], pre["points"])
            )
        med_a, med_x = statistics.median(acq), statistics.median(xfer)
        rec = {
            "requested_points": n,
            "returned_points": lengths[-1],
            "returned_points_all_equal": len(set(lengths)) == 1,
            "median_acquire_s": med_a,
            "median_transfer_s": med_x,
            "transfer_points_per_s": lengths[-1] / med_x if med_x else None,
            "sustained_frames_per_s": 1.0 / (med_a + med_x),
            "sustained_points_per_s": lengths[-1] / (med_a + med_x),
            "x_increment_s": xincs[-1],
            "x_increment_varies": len(set(xincs)) > 1,
            "x_origin_s_first": xorigs[0],
            # spread of the time-axis origin across captures: nonzero => per-record time axis needed
            "x_origin_spread_s": max(xorigs) - min(xorigs),
            "x_origin_spread_in_samples": (max(xorigs) - min(xorigs)) / xincs[-1]
            if xincs[-1]
            else None,
        }
        findings["records"][n] = rec
        print(json.dumps(rec))

    check_errors(sc, "end of run", errors)
    with (args.out / "scope_timing.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "requested_points",
                "repeat",
                "returned_points",
                "acquire_s",
                "transfer_s",
                "xorig",
                "xinc",
                "pre_points",
            ]
        )
        w.writerows(rows)
    (args.out / "scope_findings.json").write_text(json.dumps(findings, indent=2))

    print("\n=== summary for docs/probes/01-stream-semantics.md ===")
    print(f"{idn}; sample format {'unsigned' if unsigned else 'signed'} 16-bit")
    for n, r in findings["records"].items():
        print(
            f"{n:>9} pts: returned {r['returned_points']}, acquire {1e3 * r['median_acquire_s']:.1f} ms, "
            f"transfer {1e3 * r['median_transfer_s']:.1f} ms, {r['sustained_frames_per_s']:.1f} frames/s, "
            f"x_origin spread {r['x_origin_spread_in_samples']} samples"
        )
    print("instrument errors:", errors or "none")
    print(f"all outputs in {args.out}")


if __name__ == "__main__":
    main()
