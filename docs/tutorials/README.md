# Tutorials are tests

Every `*.py` here is a human-readable walkthrough that CI executes against simulated backends
(`uv run pytest docs/tutorials`). If a tutorial breaks, the build breaks. Write them as a reader
would use them: top-to-bottom, commented, no test scaffolding visible beyond a final `assert`.

Planned (one per step): `01_connect_bench.py`, `02_replay_dataset.py`, `03_define_sweep.py`, `04_query_registry.py`.
