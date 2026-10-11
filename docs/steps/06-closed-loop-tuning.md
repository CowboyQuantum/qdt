# Step 6 — Closed-loop tuning

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Calibration DAG nodes (experiment + analysis + decision) run unattended against `SimulatedDevice`, then are confirmed on hardware. Flight Deck gains gate-voltage navigation.

## Schema slice
`modeling.py`: `SimScenario`, `SimResult`, `CalibrationNode`.

## Deliverables
- DAG runner; nodes verified against sim before any L3 contact
- DAPS forward model + bias study as sim scenarios + analysis routines
- Flight Deck click-to-set (the one 'up' edge)

## L0 tests (CI)
- every DAG node passes against `SimulatedDevice` in CI; committed scenario outcomes reproduced

## L1 tests (bench loopback)
- none

## L2 tests (surrogate DUT)
- none

## Exit criteria
- a multi-node tune-up runs unattended against the sim
- first L3 contact as confirmation, not discovery

## Open decisions
- none

## Status
NOT STARTED
