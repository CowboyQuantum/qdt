# 0028 — Identity, envelope and `qdt-hdf5-v1` frozen at schema_version 1

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 3

## Context
Step 3's exit criteria are a measurement answerable by query (device, stand, definition) and the envelope
and identity slices frozen with an ADR. Both rest on PR #7 (ADR 0023–0026). The L0 ladder is green in CI
on SQLite and an ephemeral Postgres, and on 2026-10-13 also against the local compose Postgres on the
development machine (12 registry tests, 3.6 s). Running locally surfaced one operational issue: `localhost`
DSNs stalled about 5 s per connection on Windows (IPv6 first), so every DSN in the repo now names
`127.0.0.1`.

The pre-freeze review compared each object with what `Registry`, `RunRecorder`, `PayloadSource` and
Tutorial 02 actually use:

- `MeasurementRecord`: every field is read by `ingest` (cross-checked against the payload), `find`
  (`device_id`, `stand_id`, `stand_sha256`, `definition_name`, `definition_sha256`, `campaign`), or the
  table indexes. `attrs` stays free-form.
- `DeviceRecord`: `device_id`, `kind` and `simulated` are indexed. `description` and `attrs` are
  free-form. Nothing is missing for the exit query.
- **`PayloadRef.path` was unsafe.** The pattern only refused a leading `/` or `\`, so `../x.h5` or `C:/x.h5`
  validated, and `ingest` and `sync` would have written outside the payload store. The pattern now admits
  only `/`-joined segments of `[A-Za-z0-9._-]` that do not start with `.`. Every path `RunRecorder` can
  produce (`YYYY/MM/<hex>.h5`) still validates, so this is a tightening, with no version bump, by the
  argument of ADR 0022.
- `qdt-hdf5-v1`: the layout (root JSON attributes, `/data_vars`, `/coords`) carried every case the tests
  exercise: unbounded dims, streamed coordinates, annotations, plan and stand. Readers go through
  `migrations.load`.

## Decision
Freeze `identity.py` (`DeviceRecord`), `envelope.py` (`MeasurementRecord`, `PayloadRef`) and the
`qdt-hdf5-v1` payload layout at `schema_version` 1, as of the commit that carries this ADR. From here a
change to them follows the frozen-object rule (ADR, version bump, migration, old-version fixture, every
consumer in the same commit). A change to the payload layout is a new payload type (`qdt-hdf5-v2`), never an
edit of v1.

## Consequences
- Easier: Step 4 can query records and attach `AnalysisResult`s to a fixed envelope. The registry's DDL
  (ADR 0026) and the JSON Schema export of these objects are now stable references.
- Harder: adding the deferred identity objects (`CIRecord`, `AssetRecord`, `BaselineRecord`) is a new family
  with its own ADR, not an edit of this slice. A new payload spec needs a `PayloadType` literal, which is a
  schema change to `PayloadRef`, so it gets an ADR and a version bump.
- Must now: payload paths are validated where they are minted and wherever they are read. A record from an
  older client with a path the new pattern refuses cannot exist, because none was ever produced (v1 has only
  been written by `RunRecorder`).

## Alternatives considered
- Freeze without the path fix and handle traversal in `Registry._place` — rejected: the envelope is the
  contract every reader shares, and validating at the boundary protects readers that never go through
  `Registry`.
- Wait for a second payload consumer (Step 4's analysis) before freezing — rejected: Step 3's exit names
  this freeze, and Step 4 reads payloads through the same `read_payload`, which the tests already cover.
