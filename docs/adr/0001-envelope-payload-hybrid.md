# 0001 — Envelope/payload hybrid for MeasurementRecord

**Status:** Accepted
**Date:** 2026-10-09
**Step:** 4

## Context
Measurement data arrives from qdt-lab (HDF5), from external lab systems, and later from telemetry and simulation. A single strict record type would either be too loose to validate or would branch on origin in every query.

## Decision
MeasurementRecord is a small, stable provenance envelope (device ref, stand ref, timestamps, campaign, schema_version, payload_type + pointer). All strictness lives in per-payload specs (first: qdt-hdf5-v1). External systems ride the same envelope via entry-point-registered adapters.

## Consequences
- Easier: traceability queries never branch on origin; new sources are a payload type, not a table
- Harder: two levels of validation to maintain
- Must now: keep envelope required fields minimal; payload validators own strictness

## Alternatives considered
- One rich record per source — rejected: queries would branch on origin.
- Single strict universal record — rejected: cannot describe external systems without lossy mapping.
