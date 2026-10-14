# 0042 — Bench reports are written by pytest, one file per day, addresses redacted

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 5

## Context
`BENCH.md` and the development plan say every `-m hardware` run leaves a dated report in
`bench/reports/`, so the repo always shows when hardware was last proven. Nothing wrote one. The only
mechanism was a `tee` in `bench/README.md` that a human had to remember, and it was written for the
`bench/` L1/L2 suites, which do not exist yet. The first run that ever touched an instrument (the
OPX1000, through the conformance suite in `packages/qdt-lab/tests`) therefore left no record. The human
asked why.

A hand-written report also risks rule 7: a pasted pytest log carries VISA resource strings and hosts.

## Decision
- **A pytest plugin writes the report.** `scripts/bench_report.py` is loaded for every session through
  `-p bench_report` in `addopts` (`pythonpath = ["scripts"]`). It watches tests carrying the `hardware`
  marker, wherever they live: the conformance suite today, `bench/` later.
- **A run counts only if it proved something.** The report is written when at least one `hardware` test
  reached its call phase and did not skip there. A run where every instrument's address was unset
  writes nothing; CI, which deselects `hardware`, writes nothing.
- **One file per day, one section per run.** `bench/reports/<YYYY-MM-DD>-step<N>.md`, N from the
  `bench_step` ini value. A second run the same day appends a `## Run HH:MM UTC` section, so a bench
  session that works through the instruments one at a time ends with one file. Each section records
  the commit (and whether the tree was dirty), the pytest command, per-backend counts, per-test
  outcome and time, and the first line of each failure or skip message.
- **Addresses are redacted before writing.** The values of every `QDT_*_ADDRESS` variable, IPv4
  addresses, VISA resource strings and `*.stand.json` names become `<address>` / `<stand file>`. The
  report is meant to be committed without reading it first.
- The backend is read from the parametrize id in brackets, which is the conformance suite's
  convention (`[opx1000]`, `[qdac2]`, ...). Unparametrized tests show `—`.

## Consequences
- The Step 5 exit row "bench report committed" has a mechanism. Today's report records the OPX1000
  passing all seven sequencer conformance tests, the first hardware proof in the repo.
- Report sections are append-only within a day; the file is never rewritten by the plugin. Deleting a
  stale one is a human's call.
- The plugin has its own L0 tests (`packages/qdt-lab/tests/test_bench_report.py`, via `pytester`), the
  one place the "no new tests for drivers" rule does not apply: it is tooling, not a driver.
- `scripts/` is on `pythonpath` for pytest; the check scripts there become importable but nothing
  imports them.
