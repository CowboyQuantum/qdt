# qdt-registry — package rules

The only package that opens a database connection or writes SQL (rule 4). It stores schema objects;
it never defines them (that is `qdt-schemas`) and never produces data (that is `qdt-lab`).

## Layout
```
qdt_registry/
  tables.py   # SQLAlchemy Core metadata shared by the SQLite cache and Postgres; DDL_VERSION (ADR 0026); tuning_outcomes since v3 (ADR 0050); stand_states since v4 (ADR 0085)
  client.py   # Registry: cache-first writes, queries, idempotent sync (ADR 0024)
  ddl.py      # render_ddl → exports/ddl/*.sql (scripts/export_ddl.py; no-diff in check_all)
```

## Rules
- Append-only. Rows are inserted once, keyed by a client-minted id or a content hash, and never updated
  or deleted. Writing a different body under an existing key is an error, not an overwrite. The only
  mutable state is in two cache-local tables, never synced: `sync_state` and the stand server's
  `run_queue` (ADR 0086).
- The `body` column is the truth. Other columns are indexes derived from it (or from the payload), and
  every read goes through `qdt_schemas.migrations.load`.
- A table change bumps `DDL_VERSION`, regenerates the DDL export, adds an additive migration, and needs an
  ADR. Never `DROP TABLE` and never delete a migration. Migration tooling arrives with the first change
  (ADR 0026).
- Payload files are immutable. `_place` copies through a temp file and verifies the SHA-256, and an
  existing file with other content is an error.
- Tests run on SQLite always and on Postgres when `QDT_TEST_PG_DSN` is set (CI sets it; locally
  `docker compose -f deploy/registry.compose.yml up -d`). A server test must pass on both.
