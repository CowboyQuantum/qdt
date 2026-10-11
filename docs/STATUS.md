# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `step-0/close` (Step 0 closeout; merge to `main`, then start `step-1/dataset-contract`)
**Last session:** 2026-10-11 — Step 0 closed: all exit criteria met; step files and this file updated.

## Done
- Step 0 complete. CI is green on `main` (`b8d41e7`, remote `CowboyQuantum/qdt`); ADR 0001–0007 merged; `FINISH_LINE.md` has no open TODOs.
- Workspace skeleton, CLAUDE.md hierarchy, slash commands, CI, check scripts, `docs/steps/00–08`.
- `qdt-schemas`: `QdtModel` base + `ChannelMap` stub (Step 2 slice, NOT frozen).
- `qdt-lab`: `DCSource` protocol + `SimulatedDCSource` + 3-test conformance stub.
- Full Apache-2.0 LICENSE; `.gitattributes` forces LF.

## In flight
- `step-0/close` not yet merged to `main`.

## Open inputs (need lab access; human has none at present)
Both feed the Step 1 throughput benchmark that resolves Open Decisions #8 and #9:
1. Largest 2D map to render (shape, dtype).
2. Fastest OPX chunk rate (chunks/s, chunk shape) — the L1 probe measures this.

Until they are supplied, the contract draft, the synthetic source, and the benchmark use **provisional** values, labelled as provisional in code and docs. The Step 1 exit criteria (contract freeze, #8/#9 ADRs, "measured chunk rate") cannot be met until they are measured.

## Known broken / not yet real
- `FINISH_LINE.md` header still reads "SKELETON" and "Step 2 entry gate" (Step 0 says Step 1); the "add rows from prior Flight Deck / gatepick work" item was ticked with no rows added. The rendering-cases item was removed; it is now tracked here and in the Step 1 Open decisions.
- `docs/BENCH.md` is a skeleton; the Step 1 L1 probe writes the stream envelope into it (needs lab).
- Surrogate DUT not built (needed by Step 5 entry).

## Next action
Merge `step-0/close` to `main`. Then Step 1 session (2), on `step-1/dataset-contract`: draft `data.py` (`Dataset`, `DatasetChunk`, `Annotation`, `SourceDescriptor`) per ADR 0005, plus a `synthetic` source in `qdt-lab/stream/` that emits a provisional envelope. Read `packages/qdt-schemas/CLAUDE.md` and `packages/qdt-lab/CLAUDE.md` first.

## Decisions pending (see plan §12)
#8 stream transport, #9 Flight Deck stack — resolved by the Step 1 throughput benchmark (blocked on the open inputs above). #10 DUT design — by Step 5 entry.
