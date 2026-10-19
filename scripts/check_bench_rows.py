"""Every bench test names the plan that asked for it (ADR 0071).

Each `bench/test_*.py` declares a module-level `PLANNED_BY` tuple of strings, read here without importing
the module (the bench's imports need vendor SDKs). An entry is one of:

    "ADR NNNN"                  an accepted ADR in docs/adr/README.md's index
    "docs/steps/<file>.md"      a step file that names this test file

A bench test with neither is work nobody planned: file an issue instead (CLAUDE.md, Discipline).
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_ROW = re.compile(r"^\| (\d{4}) \|.*\| ([^|]*) \|\s*$")


def accepted_adrs() -> set[str]:
    index = (ROOT / "docs/adr/README.md").read_text().splitlines()
    return {
        m.group(1)
        for line in index
        if (m := ADR_ROW.match(line)) and m.group(2).strip().startswith("Accepted")
    }


def planned_by(path: Path) -> tuple[str, ...] | None:
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PLANNED_BY" for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            return (value,) if isinstance(value, str) else tuple(value)
    return None


def problems(path: Path, accepted: set[str]) -> list[str]:
    refs = planned_by(path)
    if not refs:
        return ["declares no PLANNED_BY (an accepted ADR or a step file that names it)"]
    out = []
    for ref in refs:
        if m := re.fullmatch(r"ADR (\d{4})", ref):
            if m.group(1) not in accepted:
                out.append(f"{ref!r} is not an accepted ADR in docs/adr/README.md")
        elif ref.startswith("docs/steps/"):
            step = ROOT / ref
            if not step.is_file():
                out.append(f"{ref!r} does not exist")
            elif path.name not in step.read_text():
                out.append(f"{ref!r} does not name {path.name}")
        else:
            out.append(f"{ref!r} is neither 'ADR NNNN' nor 'docs/steps/<file>.md'")
    return out


def main() -> int:
    accepted = accepted_adrs()
    bad = [
        f"{path.relative_to(ROOT)}: {problem}"
        for path in sorted((ROOT / "bench").glob("test_*.py"))
        for problem in problems(path, accepted)
    ]
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
