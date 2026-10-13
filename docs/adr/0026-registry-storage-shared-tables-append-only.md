# 0026 — Registry storage: one table set for cache and server, append-only, payloads in a file store

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 3

## Context
ADR 0024 decided that registry clients write to a local cache first and sync to Postgres. ADR 0025 made
`MeasurementRecord` a reference-and-hash envelope, with stands, definitions and plans content-addressed.
Step 3 is the first DDL in the project (plan §4.1), so the storage shape set here is what every later
migration starts from. Still open after those ADRs: what the tables are, how the cache relates to the
server, where payload bytes live on the server side, and how table changes will be managed. Docker was not
yet available on the development machine, so Postgres had to be optional for local tests and mandatory
in CI.

## Decision
One SQLAlchemy Core metadata (`devices`, `objects`, `records`, `registry_meta`) defines both the SQLite
cache and the Postgres server. Every row is append-only and stores the object's JSON `body` next to
indexed columns derived from it. The cache adds only a `sync_state` table. Payload bytes live in a
filesystem payload store on each side (`<root>/payloads`, `QDT_PAYLOAD_STORE`), addressed by the record's
relative path, and never in the database. Tables are created with `create_all` and a recorded
`ddl_version`. The first change to an existing table introduces Alembic, as an additive migration.

## Consequences
- Easier: sync is copying rows between two databases with the same schema, and "insert if absent, refuse
  a different body" is the whole conflict policy. One DDL export (`exports/ddl/*.sql`) documents both
  sides, and the no-diff check keeps it honest. The test suite runs the same server tests on SQLite
  everywhere and on Postgres when `QDT_TEST_PG_DSN` is set (CI: an ephemeral `postgres:17.6` service).
- Easier: payload files can be large (a 2048² float64 map is about 32 MB) without bloating the database or its
  backups, and a payload can be verified independently by its SHA-256.
- Harder: the server's payload store is a directory, so for Step 3 every syncing client needs that
  directory mounted (localhost here). Object storage or an HTTP upload endpoint replaces it when a second
  machine syncs, which is Step 7 lab deployment. That is an ADR then.
- Harder: SQLite constrains the shared types to the common subset: JSON (JSONB on Postgres), aware
  timestamps and plain strings. Postgres-only features (JSONB path queries inside bodies) need a
  Postgres-only code path.
- Must now: `DDL_VERSION` matches what the server reports, and a client refuses a server with a different
  version. Clients never alter a server's tables. `deploy/registry.compose.yml` is for development only
  (localhost, development credentials). Lab deployment belongs to the internal extension (plan §5).

## Alternatives considered
- Separate cache and server schemas, e.g. a JSON-lines outbox as the cache — rejected: two schemas drift,
  and the cache could not answer the exit query offline.
- Payload bytes in Postgres (`bytea` or large objects) — rejected: it bloats backups and `pg_dump`
  graduation (plan §5), it is slow for 10–100 MB maps, and it couples payload reads to a database
  connection, which `qdt-analysis` must never need (rule 5).
- Alembic from the start — rejected for now: with no existing table to change, it would only wrap
  `create_all`. It comes with the first real migration, which also forces the additive-only rule to be
  written down in code.
