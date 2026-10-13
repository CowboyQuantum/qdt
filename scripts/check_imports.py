"""Rules 1, 4, 5, 8: static import-boundary check. Extend FORBIDDEN as packages grow."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "packages/qdt-schemas/src": [r"^\s*(from|import)\s+qdt_(?!schemas)"],  # rule 1
    "packages/qdt-analysis/src": [r"^\s*(from|import)\s+(qdt_registry|sqlalchemy|psycopg|h5py)"],  # rule 5
    "packages/qdt-lab/src": [r"^\s*(from|import)\s+(sqlalchemy|psycopg)"],  # rule 4
    "packages/qdt-sim/src": [r"^\s*(from|import)\s+(qdt_registry|sqlalchemy|psycopg)"],  # rule 4
    "apps/flightdeck/src": [r"qdt_lab\.drivers", r"\bqm\.", r"qcodes", r"pyvisa"],  # rule 8
    "packages/qdt-server/src": [r"^\s*(from|import)\s+(sqlalchemy|psycopg|h5py)"],  # stores via qdt-registry only
}
bad = []
for rel, pats in FORBIDDEN.items():
    base = ROOT / rel
    if not base.exists():
        continue
    for p in base.rglob("*"):
        if p.suffix not in {".py", ".ts", ".tsx"}:
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if any(re.search(pat, line) for pat in pats):
                bad.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
if bad:
    print("check_imports: FAIL\n  " + "\n  ".join(bad))
    sys.exit(1)
print("check_imports: OK")
