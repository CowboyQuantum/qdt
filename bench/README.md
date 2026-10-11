# bench/ — hardware-in-the-loop (L1/L2)

Excluded from CI by the `hardware` marker. Run from the bench described in `docs/BENCH.md`:

    uv run pytest bench/ -m hardware | tee bench/reports/$(date +%F)-stepN.md

and commit the report. These suites reuse the conformance tests from `packages/qdt-lab/tests`; the only
bench-specific code is backend construction (addresses from `docs/BENCH.md`) and L2 golden-fixture comparisons.
