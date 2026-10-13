# Tutorials are tests

Every `*.py` here is a human-readable walkthrough that CI executes against simulated backends
(`uv run pytest docs/tutorials`). If a tutorial breaks, the build breaks. Write them as a reader
would use them: top-to-bottom, commented, no test scaffolding visible beyond a final `assert`.

| Tutorial | Shows |
|---|---|
| `test_00_smoke.py` | the workspace imports |
| `test_01_sweep.py` | declare a sweep, run it on the simulated device, stream it |
| `test_02_registry.py` | record a run, store it in the registry, find it, replay it |
| `test_03_analysis.py` | analyse a recorded run from a query, keep the result, replay it with overlays |
