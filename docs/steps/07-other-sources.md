# Step 7 — Other sources onto the substrate

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Cryo context (cooldown history, per-measurement fridge state), CI register, and the internal extension package ride the same envelope. Substrate pilot demonstration. (Lab PC deployment and IT moved to Step 6c, ADR 0073.)

## Schema slice
`cryo.py`: `CooldownRecord`, `FridgeEvent`. (`TelemetryChannel`, `TelemetrySample` deferred until a consumer needs them — ADR 0051.)

## Deliverables
- `qdt-telemetry` ingest adapter against the lab's existing fridge logs/monitoring store (ADR 0051): produces `CooldownRecord`s and attaches cryo context to `MeasurementRecord`s; raw logs optionally retained as payload files. No daemon, no time series, no dashboards.
- internal extension package: adapters, seeds, compose bundle, runbook (separate repo)
- graduation per plan §5 when the pilot outgrows the lab PC

## L0 tests (CI)
- golden-file ingest tests (fixture log corpus → expected `CooldownRecord`s and cryo context); adapter contract tests

## L1 tests (bench loopback)
- one real cooldown ingested from the lab's monitoring store; a measurement's cryo context visible in Flight Deck and by query; remote query from an office desktop

## L2 tests (instrument-on-instrument)
- none

## Exit criteria
- one stand's measurements, stand config, CI register, and cooldown history queryable in one place
- ≥1 external-system record via the same path

## Open decisions
- #7 log access mode (#6 lab PC OS moved to Step 6c, ADR 0073)

## Status
NOT STARTED
