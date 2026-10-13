# Step 4 — Analysis as a consumer

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Fits and feature detection run from registry queries, emit `AnalysisResult` with dual provenance, and render as `Annotation` overlays in Flight Deck.

## Schema slice
`modeling.py`: `FitModel`, `AnalysisResult`. Frozen at exit.

## Deliverables
- `qdt-analysis`: pure functions; Coulomb diamond pipeline (detection/estimation split) as first consumer; charge-transition detection on simulated stability diagrams
- Flight Deck overlay layer

## L0 tests (CI)
- injection–recovery in CI on synthetic and `SimulatedDevice` data
- `AnalysisResult` carries measurement ref + scenario ref; missing either fails validation

## L1 tests (bench loopback)
- none

## L2 tests (surrogate DUT)
- none

## Exit criteria
- a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset

## Open decisions
- Resolved 2026-10-13: a source–drain bias across the sensor SET (ADR 0031); diamonds are a scenario.
- What `ScenarioRef` means for live data is Step 5's (ADR 0029).

## Status
IN PROGRESS (opened 2026-10-13). Session 13: scenario ref decided (ADR 0029); `modeling.py` built, not
frozen; charge-transition detector and Coulomb diamond pipeline (bias in the model, ADR 0031) with
injection–recovery in CI; `analyses` table and DDL migration (ADR 0030); overlays on replay; Tutorial 03.
Remaining: Flight Deck demo seen by a human, freeze ADR.
