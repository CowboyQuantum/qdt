# bench/ — hardware-in-the-loop (L1/L2)

Excluded from CI by the `hardware` marker. Run from the bench described in `docs/BENCH.md`:

    uv run pytest packages/qdt-lab -m hardware     # conformance suite on the real instruments
    uv run pytest bench/ -m hardware               # L1 loopback and L2 instrument-on-instrument

Every run that executes at least one `hardware` test appends a section to
`bench/reports/<YYYY-MM-DD>-step<N>.md` (`scripts/bench_report.py`, loaded from `pyproject.toml`;
addresses are redacted). Commit the report. These suites reuse the conformance tests from
`packages/qdt-lab/tests`; the only bench-specific code is backend construction (addresses from the
`QDT_*_ADDRESS` variables) and the L2 instrument-on-instrument oracles (ADR 0040).
