# 0025 — `MeasurementRecord` is a reference-and-hash envelope; Step 3 builds only device identity

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 3

## Context
ADR 0001 made `MeasurementRecord` a small provenance envelope, with strictness in per-payload specs. Step 3
must make any simulated measurement "answerable by query (device, stand, definition)". The plan's §4.1 lists
five Step 3 objects (`MeasurementRecord`, `DeviceRecord`, `CIRecord`, `AssetRecord`, `BaselineRecord`), but
nothing in the repo defines the last three. The human chose on 2026-10-13 to build only what the exit query
needs and to let the others enter, each with a defining ADR, in the step that first consumes them. That is
the same §4.1 rule every other family follows.

What a run already produces, from Step 2: a frozen `StandConfig`, `SweepDefinition` and `ExecutionPlan`
(which embeds the `Dataset` declaration), and the data. ADR 0024 requires client-minted ids, so that
offline records never conflict. ADR 0023 puts the payload spec in `qdt-schemas[hdf5]`.

## Decision
`identity.py` holds `DeviceRecord` only. `envelope.py` holds `MeasurementRecord`: ids and content hashes of
the device, stand and definition, the plan id, the source kind, timestamps, outcome, an optional campaign,
and a `PayloadRef` (type, store-relative path, SHA-256, size). The record never embeds configurations or
arrays. The stand, plan and annotations travel inside the `qdt-hdf5-v1` payload as canonical JSON, and the
registry indexes them by `QdtModel.content_sha256()`: SHA-256 of JSON with sorted keys and no whitespace.
Every stored type is listed in `migrations.PERSISTED` and is read back through `migrations.load`.

## Consequences
- Easier: "same experiment" and "same stand" are hash equality, so the exit query is an index lookup, and
  identical definitions written offline by two clients deduplicate for free. The envelope stays small
  enough to sync cheaply. A payload file is self-describing without the registry, because its definition,
  plan and stand are inside it.
- Easier: one `upgrade`/`load` path and one fixture tree (`tests/fixtures/<Type>/v<n>.json`, written by
  `scripts/make_schema_fixtures.py`, never rewritten) cover every persisted type. `records.schema.json`
  exports them.
- Harder: a content hash depends on the JSON form. Any change to a persisted type's serialization, even a
  non-breaking added field with a default, changes the hashes of new objects. The registry must therefore
  store a hash alongside its object, never recompute it to match old rows, and treat a hash as identifying
  an object at its stored `schema_version`.
- Harder: queries by fields inside the stand or definition (for example, "every sweep of channel P2") need
  the registry to store and index those objects. Envelope fields alone do not answer them.
- Must now: every type the registry or a payload stores joins `PERSISTED`, with a fixture. `CIRecord`,
  `AssetRecord` and `BaselineRecord` stay undefined until a step consumes them, so plan §4.1 lists them
  as deferred. Record ids match `^[0-9a-f]{32}$` (UUID4 hex). Payload paths are relative and
  '/'-separated. Timestamps on new types are timezone-aware (`AwareDatetime`).

## Alternatives considered
- Embed the `StandConfig` and `SweepDefinition` in the record — rejected: it bloats every row and every sync
  with repeated, identical configuration, and contradicts ADR 0001's small envelope.
- Database-assigned ids or surrogate keys for stands and definitions — rejected: they are incompatible with
  offline writes (ADR 0024). Content addresses are stable everywhere without coordination.
- Guess definitions for `CIRecord`, `AssetRecord` and `BaselineRecord` now — rejected by the human: a frozen
  schema built on invented semantics is worse than a later, deliberate addition.
