# 0024 — Registry clients write to a local cache first and sync to Postgres (closes #4)

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 3

## Context
Step 3 makes Postgres (`QDT_REGISTRY_DSN`) the registry of measurement records. Plan §12 decision #4 had a
working assumption to confirm at Step 3: clients keep a local cache and sync. The forces:

- Measurements must never fail or be lost because a database is unreachable. A laptop on a prober, a bench
  PC on a flaky network, or a server under maintenance must not stop a run.
- Records carry full provenance and are immutable once written. Two clients never edit the same record; they
  only add new ones.
- Rule 4: only `qdt-registry` opens a database connection or writes SQL. That covers both the local cache and
  the remote database.

The human confirmed cache + sync on 2026-10-13.

## Decision
`qdt-registry`'s client writes every record to a local cache first, in the same call that commits the
payload file, and uploads it to Postgres when a connection is available. Record ids are client-generated
UUIDs, and uploads are idempotent, so retrying a sync is always safe and records never conflict.

## Consequences
- Easier: a run's success never depends on the network. Sync is append-only (insert-if-absent by id), so it
  needs no conflict resolution. Queries against the local cache work offline for that client's own records.
- Harder: there are two stores to keep consistent, the cache schema must follow the Postgres schema through
  migrations, and "is it uploaded yet" becomes a visible state that callers and Flight Deck may need to show.
- Must now: record ids are UUIDs minted by the client, never database sequences. The cache is the
  source of truth until upload is confirmed. Sync is resumable and safe to run concurrently. The L0 suite
  covers write offline → sync → query remote, and a repeated sync that writes nothing. The cache backend
  (SQLite via SQLAlchemy is the default candidate) is chosen in the first registry commit and recorded
  there or in a follow-up ADR if it is not SQLite.

## Alternatives considered
- Online-only, with cache + sync deferred — rejected by the human: losing or blocking a run because of the
  network is the failure the registry exists to prevent, and retrofitting client-minted ids later would mean
  a migration of every stored record.
- Remote-first with a local retry queue for failures only — rejected: the client then has two write paths
  (normal and degraded), and only the rarely exercised one handles the hard case.
