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
- none

## Status
DONE (2026-10-13). Exit criteria met: query → method → `AnalysisResult` → overlays on the originating
dataset, seen in Flight Deck; injection–recovery in CI for transitions (synthetic lattices, noisy
simulated sweeps) and diamonds (synthetic train, simulated cold sensor); `modeling.py` frozen (ADR 0033).
ADRs 0029–0031, 0033. The Coulomb diamond deliverable needed a source–drain bias in the model (ADR 0030).
