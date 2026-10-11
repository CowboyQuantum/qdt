# qdt-schemas — package rules

This package is the root of the dependency tree and the product itself. It imports **nothing** from any other `qdt-*` package (rule 1) and depends only on pydantic (+ optional `[hdf5]`).

## Adding or changing a schema
1. Check which roadmap step first consumes the family (plan §4.1). Do not add a family ahead of its step.
2. Every model inherits `QdtModel` (`_base.py`): frozen, `extra="forbid"`, carries `schema_version`.
3. Every field has `description=`. `scripts/check_descriptions.py` fails CI otherwise — descriptions generate the schema docs.
4. Breaking change → bump that object's `schema_version` and add a pure-dict transform in `migrations.py`; add a fixture at the old version under `tests/fixtures/` so the migration test covers it.
5. Same commit: schema + every consumer + migration + tests. Then `uv run pytest` must pass workspace-wide.
6. From Step 4: regenerate JSON Schema and DDL exports; CI checks for no diff.

## Never
- import numpy/xarray/h5py at module top level (keep this package light; `[hdf5]` imports lazily)
- edit a model that a frozen step owns without an ADR
