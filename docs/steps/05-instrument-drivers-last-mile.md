# Step 5 — Instrument drivers (the last mile)

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Real drivers behind the protocols. Everything above already works against `Simulated*`; this step proves the simulated backends were honest. First `bench/` reports.

## Schema slice
None new. `InstrumentConfig` gains vendor address fields only if required (minor bump).

## Deliverables
- `docs/BENCH.md` complete, including the bias tee's and the scope's specifications for L2 (ADR 0040)
- `qdt-lab/drivers/`: OPX, QDAC-II, Keysight scope, SMU — each behind an extra (ADR 0006), each registered in the conformance parametrization
- `bench/` L1 loopback and L2 instrument-on-instrument suites; dated reports committed
- curated `qdt-analysis` methods for L2: plane fit (with iso-line overlays) and single exponential

## L0 tests (CI)
- conformance suite unchanged and green on `Simulated*`
- extras matrix green

## L1 tests (bench loopback)
- QDAC→scope, SMU→scope, OPX out→scope loopbacks with numeric oracles
- `StandConfig` validates against the enumerated bench

## L2 tests (instrument-on-instrument)
- L2-1: QDAC DC × OPX pulse through the bias tee, read by the stage `measure` on an OPX input; a plane with specified coefficients, live in Flight Deck, recorded in the registry, fitted by `qdt-analysis`, overlays drawn
- L2-2: QDAC and SMU current readout into the scope's 1 MΩ input (I = V / 1 MΩ)
- L2-3: the bias tee's droop on an OPX step, captured by the scope; single-exponential fit against its specification

## Exit criteria
- conformance suite passes on all four real instruments under `-m hardware`
- one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay
- bench report committed

## Open decisions
- #10 surrogate DUT design — closed by ADR 0040 (no board)

## Status
NOT STARTED
