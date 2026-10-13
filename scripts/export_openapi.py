"""Export qdt-server's OpenAPI document; `--check` fails on drift (run in check_all, ADR 0034).

`packages/qdt-server/exports/openapi.json` is what Flight Deck generates its API types from
(`pnpm gen:api`), as `src/schema/data.ts` comes from `data.schema.json`. Regenerate after any change to
the routes or to a schema object they carry: `uv run python scripts/export_openapi.py`.
"""

import json
import pathlib
import sys
import tempfile

from qdt_server import Settings, create_app

OUT = pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-server/exports/openapi.json"


def render() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(root=pathlib.Path(tmp), stream_port=0))
        return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("export_openapi: DRIFT — run `uv run python scripts/export_openapi.py`")
            return 1
        print("export_openapi: OK")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
