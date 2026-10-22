"""ADR 0079: the general layer knows no domain words. A ratchet: hits may only go down.

Scans the general packages for the terms in scripts/vocabulary_terms.txt and compares against
scripts/vocabulary_baseline.txt. New hits fail; removed hits are reported so the baseline can shrink.
Regenerate the baseline (only after removing hits, never to admit new ones):
    uv run python scripts/check_vocabulary.py --write-baseline
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERAL = ["packages/qdt-schemas/src", "packages/qdt-lab/src", "packages/qdt-registry/src"]
TERMS = [t.strip() for t in (ROOT / "scripts/vocabulary_terms.txt").read_text().splitlines() if t.strip() and not t.startswith("#")]
PAT = re.compile(r"\b(" + "|".join(re.escape(t) for t in TERMS) + r")\b", re.I)
BASELINE = ROOT / "scripts/vocabulary_baseline.txt"


def hits():
    out = []
    for rel in GENERAL:
        for p in (ROOT / rel).rglob("*.py"):
            for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                m = PAT.search(line)
                if m:
                    out.append(f"{p.relative_to(ROOT)}:{m.group(1).lower()}")
    return sorted(out)


def main():
    now = hits()
    if "--write-baseline" in sys.argv:
        BASELINE.write_text("\n".join(now) + "\n")
        print(f"check_vocabulary: baseline written ({len(now)} hits)")
        return
    base = sorted(BASELINE.read_text().splitlines()) if BASELINE.exists() else []
    new = sorted(set(now) - set(base))
    gone = sorted(set(base) - set(now))
    if gone:
        print("check_vocabulary: hits removed (shrink the baseline with --write-baseline):\n  " + "\n  ".join(gone))
    if new:
        print("check_vocabulary: FAIL — domain words in the general layer (ADR 0079):\n  " + "\n  ".join(new))
        sys.exit(1)
    print(f"check_vocabulary: OK ({len(now)} baseline hits remain)")


if __name__ == "__main__":
    main()
