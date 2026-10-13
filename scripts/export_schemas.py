"""Export JSON Schema for qdt-schemas; `--check` fails on drift (run in check_all).

- `data.schema.json`: the stream contract. Flight Deck generates its TypeScript types from it
  (`pnpm gen:types`, ADR 0005/0006).
- `records.schema.json`: every type the registry or a payload stores, `migrations.PERSISTED` (ADR 0025).

Regenerate after any schema change: `uv run python scripts/export_schemas.py`.
"""

import json
import pathlib
import sys

from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema

from qdt_schemas.data import (
    Annotation,
    AnnotationMessage,
    Dataset,
    DatasetChunk,
    DatasetMessage,
    StreamTextMessage,
)
from qdt_schemas.migrations import PERSISTED

DIR = pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-schemas/exports/jsonschema"


def render() -> str:
    _, schema = models_json_schema(
        [
            (m, "serialization")
            for m in (Dataset, DatasetChunk, Annotation, DatasetMessage, AnnotationMessage)
        ],
        title="qdt Dataset stream contract",
    )
    text_message = TypeAdapter(StreamTextMessage).json_schema(
        mode="serialization", ref_template="#/$defs/{model}"
    )
    schema["$defs"]["StreamTextMessage"] = {k: v for k, v in text_message.items() if k != "$defs"}
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def render_records() -> str:
    _, schema = models_json_schema(
        [(PERSISTED[name], "serialization") for name in sorted(PERSISTED)],
        title="qdt registry records",
    )
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    outputs = {DIR / "data.schema.json": render(), DIR / "records.schema.json": render_records()}
    if "--check" in sys.argv:
        drift = [
            p.name
            for p, text in outputs.items()
            if not p.exists() or p.read_text(encoding="utf-8") != text
        ]
        if drift:
            print(f"export_schemas: DRIFT — run `uv run python scripts/export_schemas.py` {drift}")
            return 1
        print("export_schemas: OK")
        return 0
    DIR.mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
