# Step 7 — Other sources onto the substrate

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Telemetry, cooldown history, CI register, and the internal extension package ride the same envelope. Lab PC deployment and IT engagement. Substrate pilot demonstration.

## Schema slice
`cryo.py`: `CooldownRecord`, `FridgeEvent`, `TelemetryChannel`, `TelemetrySample`.

## Deliverables
- `qdt-telemetry` parsers against fixture logs
- internal extension package: adapters, seeds, compose bundle, runbook (separate repo)
- IT checklist (plan §9) sent; lab PC deployment; graduation per plan §5

## L0 tests (CI)
- golden-file parser tests; adapter contract tests

## L1 tests (bench loopback)
- live fridge logs ingested; remote query from an office desktop

## L2 tests (surrogate DUT)
- none

## Exit criteria
- one stand's measurements, stand config, CI register, and cooldown history queryable in one place
- ≥1 external-system record via the same path

## Open decisions
- #5 manager sign-off (gates this step only)
- #6, #7 lab PC OS and log access mode

## Status
NOT STARTED
