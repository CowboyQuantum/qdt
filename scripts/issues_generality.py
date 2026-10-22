"""File ADR 0079's generality work as GitHub issues (label `generality`). Dry run by default.

    uv run python scripts/issues_generality.py            # print
    uv run python scripts/issues_generality.py --apply    # needs `gh auth login`
"""
import json
import subprocess
import sys

ISSUES = [
    ("Widen Quantity and DType (ADR 0079 §3)", "Add frequency, power, phase, resistance, temperature, time, dimensionless to `Quantity` with SI units; add complex64/complex128 to `DType` with interleaved-pair transport. Minor schema_version bump, no migration. Do first: it has a deadline (before more slices depend on the narrow literals).", ["generality", "schemas"]),
    ("TraceSense protocol: instrument-supplied axis of any quantity (ADR 0079 §4)", "A capture protocol whose axis the instrument supplies; `WaveformSense` becomes its time-axis case. Emulator + conformance rows; scope driver implements it first.", ["generality", "lab"]),
    ("Second-domain suite: IV curve on the SMU (ADR 0079 §5)", "Host-stepped level sweep with current sense and a line fit, kept green in L0 against the SMU emulator; an L2 row on the home bench. Proves the claim at zero cost.", ["generality", "lab", "analysis"]),
    ("Second-domain suite: FFT of a captured waveform (ADR 0079 §5)", "One generic FFT method in qdt-analysis (complex output); captures recorded as payloads; L0 against the scope emulator; L2 on the home bench.", ["generality", "analysis"]),
    ("Second-domain suite: S-parameter sweep on an emulated VNA (ADR 0079 §5)", "Needs the Quantity/DType widening and TraceSense. VNA emulator only until a real one exists; complex Dataset end to end into Flight Deck.", ["generality", "lab", "flightdeck"]),
    ("Flight Deck categories from stand data, not code (ADR 0079 §6)", "Channel types and stages shown in Levels/Sweep come from the stand configuration; no gate vocabulary in the widget code.", ["generality", "flightdeck"]),
    ("Rename the four baseline vocabulary hits when touched (ADR 0079 §2)", "`virtual gate` in activity/compile/execute → a neutral name for a linear channel transform; `cooldown` in envelope → a neutral run-context name; with migrations. Shrink scripts/vocabulary_baseline.txt.", ["generality", "schemas", "lab"]),
]


def main():
    if "--apply" not in sys.argv:
        print(json.dumps([{"title": t, "labels": l} for t, _, l in ISSUES], indent=1)); print(f"\n{len(ISSUES)} issues (dry run)", file=sys.stderr); return
    subprocess.run(["gh", "label", "create", "generality", "--color", "5319e7", "--force"], check=False, capture_output=True)
    for title, body, labels in ISSUES:
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body, *[a for x in labels for a in ("--label", x)]], check=True)
        print("created:", title)


if __name__ == "__main__":
    main()
