# Step 5 — Instrument drivers (the last mile)

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Real drivers behind the protocols. Everything above already works against `Simulated*`; this step proves the simulated backends were honest. First `bench/` reports.

## Schema slice
None new. `InstrumentConfig` gains vendor address fields only if required (minor bump).

## Deliverables
- `docs/BENCH.md` complete; surrogate DUT built and hand-characterized (golden fixture)
- `qdt-lab/drivers/`: OPX, QDAC-II, Keysight scope, SMU — each behind an extra (ADR 0006), each registered in the conformance parametrization
- `bench/` L1 loopback and L2 surrogate-DUT suites; dated reports committed

## L0 tests (CI)
- conformance suite unchanged and green on `Simulated*`
- extras matrix green

## L1 tests (bench loopback)
- QDAC→scope, SMU→scope, OPX out→scope loopbacks with numeric oracles
- `StandConfig` validates against the enumerated bench

## L2 tests (surrogate DUT)
- declared IV sweep reproduces the diode curve; declared 2D sweep reproduces the divider surface, live in Flight Deck, recorded in the registry, fitted by `qdt-analysis`

## Exit criteria
- conformance suite passes on all four real instruments under `-m hardware`
- one end-to-end L2 run: definition → hardware → Flight Deck → registry → overlay
- bench report committed

## Open decisions
- #10 surrogate DUT design (if not already resolved)

## Status
NOT STARTED
