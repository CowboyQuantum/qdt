# Step 3 — Measurement registry

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Records land in a remote-capable database with full provenance, and the registry becomes a first-class Flight Deck source. First DDL.

## Schema slice
`identity.py`, `envelope.py`: `MeasurementRecord`, `DeviceRecord`, `AssetRecord`, `CIRecord`, `BaselineRecord`; `payload_hdf5.py` v1; `migrations.py`. JSON Schema + DDL exports begin.

## Deliverables
- `qdt-registry`: Postgres via `QDT_REGISTRY_DSN`, localhost compose on personal hardware, client with offline cache + sync
- executor writes a `MeasurementRecord` per run
- Flight Deck `registry` source; datasets addressable by record ref

## L0 tests (CI)
- ephemeral Postgres in CI: write → query round trip
- migration fixtures at every `schema_version`
- JSON Schema and DDL export no-diff
- full loop: Step 2 sweep on `SimulatedDevice` → record → Flight Deck replays from registry

## L1 tests (bench loopback)
- none

## L2 tests (surrogate DUT)
- none

## Exit criteria
- any simulated measurement answerable by query (device, stand, definition)
- envelope + identity slices frozen with ADR

## Open decisions
- #2 `payload_hdf5` location — CLOSED by ADR 0023: `qdt-schemas[hdf5]` extra
- #4 offline cache + sync — CLOSED by ADR 0024: cache first, idempotent sync, client-minted UUIDs

## Status
IN PROGRESS (opened 2026-10-12; no code yet)
