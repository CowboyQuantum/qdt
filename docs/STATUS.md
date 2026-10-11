# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `main`
**Last session:** 2026-10-11 (chat) — ADR 0008 + Analysis 0001 closed the "open inputs"; Probe 01 spec and scripts added.

## Done
- Step 0 complete; CI green on `main`; ADR 0001–0008 merged; `FINISH_LINE.md` authored with design targets.
- Workspace skeleton, CLAUDE.md hierarchy, slash commands, CI, check scripts, `docs/steps/00–08`.
- `qdt-schemas`: `QdtModel` base + `ChannelMap` stub (Step 2 slice, NOT frozen).
- `qdt-lab`: `DCSource` protocol + `SimulatedDCSource` + 3-test conformance stub.
- Analysis 0001 (`docs/analysis/`) bounded map size and chunk rate by arithmetic; ADR 0008 decided WebSocket + Arrow IPC and WebGL 2D. Open Decision #8 closed; #9 reduced to library choice.
- Probe 01 spec (`docs/probes/01-stream-semantics.md`) and scripts (`bench/probes/probe01/`) written, **not yet run** — needs lab access. Gates the contract *freeze* only.

## In flight
- Nothing. Tree is clean.

## Known broken / not yet real
- Probe 01 unrun; `bench/fixtures/probe01/` empty. Contract freeze ADR cannot be written until it runs.
- Probe scripts' `qm-qua` API names unverified against the installed version (isolated per variant by design).
- `docs/BENCH.md` is a skeleton (needed in full by Step 5).
- Surrogate DUT not built (needed by Step 5 entry).

## Next action
Step 1 session (2), on `step-1/dataset-contract`: draft `data.py` (`Dataset`, `DatasetChunk`, `Annotation`, `SourceDescriptor`) per ADR 0005/0008 — `DatasetChunk` must support both implicit (index range + definition ref) and explicit coordinates pending Probe 01 — plus a `synthetic` source in `qdt-lab/stream/` emitting the Analysis 0001 envelope. Read `packages/qdt-schemas/CLAUDE.md` and `packages/qdt-lab/CLAUDE.md` first.

## Decisions pending (see plan §12)
#9 WebGL library (Step 1 benchmark, tie-breaker). Contract freeze (after Probe 01). #10 DUT design — by Step 5 entry.
