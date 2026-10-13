"""Export the registry DDL; `--check` fails on drift (run in check_all, plan §4.3).

Regenerate after any change to qdt_registry/tables.py: `uv run python scripts/export_ddl.py`.
"""

import pathlib
import sys

from qdt_registry import render_ddl

OUT = pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-registry/exports/ddl"


def main() -> int:
    outputs = {OUT / f"{d}.sql": render_ddl(d) for d in ("postgresql", "sqlite")}
    if "--check" in sys.argv:
        drift = [
            p.name
            for p, text in outputs.items()
            if not p.exists() or p.read_text(encoding="utf-8") != text
        ]
        if drift:
            print(f"export_ddl: DRIFT, run `uv run python scripts/export_ddl.py` {drift}")
            return 1
        print("export_ddl: OK")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
