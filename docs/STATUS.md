# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 0 — Bootstrap → `docs/steps/00-bootstrap.md`
**Branch:** `main`
**Last session:** 2026-10-11 — plan bumped to v0.4 (ADR 0007, simulation-first); §7 split into `docs/steps/`; pointers updated.

## Done
- Workspace skeleton, CLAUDE.md hierarchy, slash commands, ADR 0001–0007, CI scaffold, check scripts, `docs/steps/00–08`.
- `qdt-schemas`: `QdtModel` base + `ChannelMap` stub (Step 2 slice, NOT frozen).
- `qdt-lab`: `DCSource` protocol + `SimulatedDCSource` + 3-test conformance stub.
- Verified locally: 10 tests + `check_all.sh` green; `uv.lock` committed.

## In flight
- Nothing. Tree is clean.

## Known broken / not yet real
- CI has never run (no remote yet).
- `docs/FINISH_LINE.md` is a skeleton with TODOs — human-authored; it is the Step 1 entry gate.
- `docs/BENCH.md` is a skeleton; needed in full only by Step 5, but the Step 1 L1 probe writes the stream envelope into it.
- `LICENSE` is a pointer; replace with full Apache-2.0 text before first public push.
- Surrogate DUT not built (needed by Step 5 entry).

## Next action
Push to `cowboyquantum/qdt`, confirm CI green, replace LICENSE. Then the human fills `docs/FINISH_LINE.md`; that unblocks Step 1 session (2): contract draft + synthetic source.

## Decisions pending (see plan §12)
#8 stream transport, #9 Flight Deck stack — resolved by the Step 1 throughput benchmark. #10 DUT design — by Step 5 entry.
