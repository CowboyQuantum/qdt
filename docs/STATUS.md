# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 0 — Bootstrap → `docs/steps/00-bootstrap.md`
**Branch:** `step-0/push-and-license` (3 commits ahead of `main`, which holds only the initial import)
**Last session:** 2026-10-11 — git repo re-initialised (prior history was absent from this working copy); full Apache-2.0 LICENSE; `.gitattributes` (LF); git write permissions added to `.claude/settings.json`.

## Done
- Workspace skeleton, CLAUDE.md hierarchy, slash commands, ADR 0001–0007, CI scaffold, check scripts, `docs/steps/00–08`.
- `qdt-schemas`: `QdtModel` base + `ChannelMap` stub (Step 2 slice, NOT frozen).
- `qdt-lab`: `DCSource` protocol + `SimulatedDCSource` + 3-test conformance stub.
- `LICENSE` is the full, unmodified Apache-2.0 text (sha256 `cfc7749b…`).
- `.gitattributes` forces LF so `scripts/*.sh` run under Git Bash on Windows.

## In flight
- `step-0/push-and-license` not yet merged to `main` or pushed.

## Known broken / not yet real
- **`uv` is not installed on the current dev machine.** `uv run pytest` and most of `check_all.sh` were NOT run this session; only `provenance_check.sh` (OK). The "10 tests green" claim dates from an earlier machine.
- No remote configured; CI has never run.
- `docs/FINISH_LINE.md` is a skeleton with TODOs — human-authored; it is the Step 1 entry gate.
- `docs/BENCH.md` is a skeleton; needed in full only by Step 5, but the Step 1 L1 probe writes the stream envelope into it.
- Surrogate DUT not built (needed by Step 5 entry).

## Next action
Human: install `uv`, run `uv sync --all-packages --all-extras`, `uv run pytest`, `bash scripts/check_all.sh`; merge `step-0/push-and-license` to `main`; add remote `cowboyquantum/qdt` and push (pushing stays manual); confirm CI green. Then fill `docs/FINISH_LINE.md`, which unblocks Step 1 session (2): contract draft + synthetic source.

## Decisions pending (see plan §12)
#8 stream transport, #9 Flight Deck stack — resolved by the Step 1 throughput benchmark. #10 DUT design — by Step 5 entry.
