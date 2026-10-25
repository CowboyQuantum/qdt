# 0083 — Bench reports file themselves under the step that planned the test; `bench_step` is only a fallback; DSNs are redacted beside addresses

**Status:** Accepted
**Date:** 2026-10-25
**Step:** 6c (deliverable 12, issue #77; amends ADR 0042)

## Context
ADR 0042 made pytest write every hardware run into `bench/reports/<date>-step<N>.md`, with `N` from the
`bench_step` ini value in `pyproject.toml`. That value stayed at `5` through Step 6: two Step 6 runs on
2026-10-19 were moved to their file by hand (#77), and the first Step 6c run of this session landed in a
`-step5.md` file too. Since ADR 0071 every bench test already declares `PLANNED_BY`, the step file or
ADRs that asked for it, and `scripts/check_bench_rows.py` enforces it in CI, so the plan that owns a test
is machine-readable: a step file's name carries its number (`docs/steps/06c-…`) and every ADR carries a
`**Step:**` line. Deployment goal 2 is validated by bench reports; they should file themselves correctly
without anyone editing an ini value at each step boundary.

Separately, the remote-read rows (Step 6c, R-1 … R-4) put a database DSN and server addresses into the
bench environment. ADR 0042 redacts `QDT_*_ADDRESS` values, IPv4 addresses and VISA strings; a DSN
carries a password and a host name that no report may record (rule 7).

## Decision
Derive a hardware test's step from its module's `PLANNED_BY`: the number of the first step file it
names, else the `**Step:**` of the highest-numbered ADR it names whose line is a step number (the
newest ADR is the one that planned the newest row); a run that executes tests of several steps writes
a section to each step's report. `bench_step` remains only as the fallback for a test that resolves to
no step, and is removed from `pyproject.toml`, so such a test files as `-stepunplanned.md` rather than
under a stale number. Redact the values of every `QDT_*_DSN` variable and any URL that carries
credentials, alongside the address forms ADR 0042 already hides.

## Consequences
- Easier: a new step needs no ini change; a report's file name is evidence of which plan the run
  served; a mixed run (an L1 loopback and an L2 row from different steps) files each under its own step;
  the remote-read rows can print their DSN in a failure message without rule 7 being at risk.
- Harder: `bench_report` reads ADR files at report time (only the `**Step:**` line, only for ADR-planned
  tests); a test planned by ADRs from different steps files under the newest ADR's step, which is a
  heuristic — `test_opx_streaming.py` (ADR 0015, 0066) files under Step 6, where its row was proven,
  not Step 1. A test planned only by an ADR whose Step line is not a number (`process`, `all`) files as
  `unplanned` until it also names a step file.
- Must now: nothing further; existing reports keep their names (the plugin never renames a file).

## Alternatives considered
- Bump the ini value at each step boundary — rejected: that is what did not happen (#77); the
  information already exists in `PLANNED_BY`.
- Pass `-o bench_step=N` in the documented bench command — rejected: moves the forgetting from the ini
  to the command line; the runbook would carry a number that goes stale.
- Derive the step from the current milestone or `docs/STATUS.md` — rejected: a Step 5 loopback re-run
  during Step 6c is still a Step 5 proof; the test's plan, not the calendar, says where it belongs.
- Record the step per test in a marker (`@pytest.mark.step("6c")`) — rejected: a second declaration
  beside `PLANNED_BY` that can disagree with it.
