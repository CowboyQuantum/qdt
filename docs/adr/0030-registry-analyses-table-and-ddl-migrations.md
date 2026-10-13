# 0030 — The registry stores `AnalysisResult`s in an `analyses` table; DDL changes are additive migration steps

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4

## Context
Step 4's exit criterion is "a fit runs from a query, writes an `AnalysisResult`, and its overlay renders
on the originating dataset". A result has to live somewhere a later session, or `python -m qdt_registry
serve`, can find it by record. The registry (ADR 0026) had three tables (`devices`, `objects`,
`records`) at `DDL_VERSION` 1, with the rule "a table change bumps `DDL_VERSION`, regenerates the DDL
export, adds an additive migration, and needs an ADR; migration tooling arrives with the first change".
This is the first change.

Two places could hold results. The content-addressed `objects` table takes any persisted type, but it is
keyed by hash and indexed by `name`; "every analysis of record X" would need a convention on `name`.
A dedicated table has the foreign key and the indexes the question needs.

## Decision
Add `analyses` (`DDL_VERSION` 2): `analysis_id` (PK), `record_id` (FK to `records`), `dataset_id`,
`variable`, `model_name`, `scenario_kind`, `scenario_name`, `created_at`, `schema_version`, `body`;
indexed by (`record_id`, `created_at`) and (`model_name`, `created_at`). Append-only like every other
table; `body` is the truth and the other columns are indexes.

`Registry.record_analysis(result)` requires `measurement.record_id`, checks the record exists in the
client's cache, that `measurement.dataset_id` is the record's `plan_id`, that the variable exists on the
recorded Dataset, and that every annotation fits that Dataset's coordinates (`Dataset.check_annotation`,
against the plan stored in `objects`, so no payload is read). `Registry.analyses(record_id)` returns
them oldest first; `sync` uploads them after records, so the foreign key holds on the server.
`python -m qdt_registry serve` passes the record's analysis annotations to `PayloadSource`, which
announces them after the payload's own, so Flight Deck's existing overlay draws them.

`qdt_registry/migrations.py` holds `STEPS`: one function per `DDL_VERSION` bump that creates what the
version adds and never drops or rewrites. `migrate(engine)` creates everything on an empty database,
applies the steps from the stored `ddl_version` up to the current one on an older database (recording
each), and refuses a newer one. Every `Registry` open runs it on the cache, and on the server at first
use.

## Consequences
- Easier: a result is one query away from its record on both sides of a sync, and a DDL-1 database
  (any cache or server from Step 3) upgrades itself on open. The DDL export shows the added table.
- Harder: the server migrates when the first new client connects. On a shared Postgres that is a
  schema change performed by a client; two clients racing both run `CREATE TABLE IF NOT EXISTS`, which
  is safe, but the policy of *who* migrates a shared server is a Step 7 concern (deployment).
- Harder: a result on an unrecorded Dataset cannot be stored. That is deliberate: the registry answers
  "what was found on this record"; results on synthetic test maps stay in the test.
- Must now: a table change is a `STEPS` entry + `DDL_VERSION` bump + regenerated export + a migration
  test from the previous version + an ADR. Steps are idempotent (`checkfirst`), so a migration can be
  rerun after an interruption.

## Alternatives considered
- Store results in `objects` by content hash — rejected: no foreign key to the record and no index to
  answer the record query; and a result is identified by its client-minted id, not by its content (two
  identical runs of a detector are two results).
- Store results in the payload (rewrite the HDF5 with new annotations) — rejected: payloads are
  immutable (ADR 0026), and a result is produced after the run by a different actor.
- Alembic for migrations — rejected for now: one additive step does not justify a second migration
  framework next to `qdt_schemas.migrations`; `STEPS` has the same shape (from version → function) and
  can be replaced if migrations ever need to alter or backfill.
