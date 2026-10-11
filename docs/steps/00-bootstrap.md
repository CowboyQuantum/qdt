# Step 0 — Bootstrap

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Repo exists, CI is green on the L0 suite, the documentation and enforcement scaffolding is in place, and the two human-authored context documents (FINISH_LINE.md, BENCH.md) are started.

## Schema slice
None. `QdtModel` base only.

## Deliverables
- uv workspace with package skeletons, `apps/flightdeck/`, `bench/`, CI, `CLAUDE.md` hierarchy, slash commands, scripts
- `docs/DEVELOPMENT_PLAN.md`, `docs/steps/`, ADR 0001–0007, `docs/STATUS.md`
- `docs/FINISH_LINE.md` filled in by a human (Step 1 entry gate)
- Full Apache-2.0 LICENSE text; remote on `cowboyquantum/qdt`

## L0 tests (CI)
- workspace installs; `uv run pytest` and `bash scripts/check_all.sh` green in CI

## L1 tests (bench loopback)
- none

## L2 tests (surrogate DUT)
- none

## Exit criteria
- CI green on `main`
- `FINISH_LINE.md` has no open TODOs
- ADR 0007 merged

## Open decisions
- #10 surrogate DUT design — may be deferred to Step 5 entry

## Status
DONE (2026-10-11)
