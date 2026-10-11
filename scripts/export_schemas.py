"""Export JSON Schema for the qdt-schemas stream contract; `--check` fails on drift (run in check_all).

Flight Deck generates its TypeScript types from this file (`pnpm gen:types`, ADR 0005/0006).
Regenerate after any change to qdt_schemas/data.py: `uv run python scripts/export_schemas.py`.
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

OUT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "packages/qdt-schemas/exports/jsonschema/data.schema.json"
)


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


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(
                f"export_schemas: DRIFT — run `uv run python scripts/export_schemas.py` ({OUT.name})"
            )
            return 1
        print("export_schemas: OK")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
