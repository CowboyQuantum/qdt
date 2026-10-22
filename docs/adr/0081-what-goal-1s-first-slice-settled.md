# 0081 — What goal 1's first slice settled: replay stays on the read server, `/server` names the kind, scripts take payload bytes over HTTP, the read server reads as the reader role, `roles.sql` and `init` are the schema step, a read-only SQLite file is the reader's stand-in in L0

**Status:** Accepted
**Date:** 2026-10-22
**Step:** 6c (goal 1, deliverables 2–4; refines ADR 0074 and 0080 where the code had to choose)

## Context
Session 27 built goal 1's first slice: the sync after every record (ADR 0080), `qdt-server --read-only`
(ADR 0074), and the script read path with its tutorial. Five choices were not written down anywhere and
a later session would ask why; one open decision in `STATUS.md` (how a script gets payload bytes) closed.

## Decision
1. **`POST /stream/replay` exists on the read server.** Step 6c's L0 row said "every `POST`/`DELETE` is
   404/405"; ADR 0074 lists replay among what the read server serves. Replay commands nothing: it puts a
   stored payload on the server's own stream for Flight Deck to draw. So the rule is *every route that
   needs a stand or writes the registry is absent*: `/stand`, `/levels*`, `/sweeps/compile`, `/runs*`,
   `POST /records/{id}/results` (it writes a result), `/nodes`, `/tuneups*`. They sit on one `APIRouter`
   included only on a stand server, so the read server's OpenAPI document is the read contract as built,
   not a filtered copy. The step file's row is reworded accordingly.
2. **`GET /server` → `ServerInfo {read_only, stand_id, device_id}`** is how Flight Deck learns which kind
   of server answered; an unreachable server is treated as a stand server. Against a read server the
   command widgets are not registered and the strip's Run cluster is not built (absent, not disabled,
   ADR 0074); the read server's layout persists under its own key so one browser can face both kinds.
   `ServerInfo` is a server-side body like `StreamInfo` and `RunRequest` (ADR 0034), not a schema object:
   it describes the API's own deployment, which no other tool exchanges.
3. **A script takes payload bytes over HTTP, never from the share.** `Registry(root, remote_dsn=<reader>)`
   reads devices, records and results with `remote=True`; `payload(…, remote=True)` works only where the
   server's store is local (the read server) and otherwise says to use `GET /records/{id}/payload`, whose
   `X-Content-SHA256` the reader checks against the record. The share is mounted by stand servers only
   (ADR 0074's rule holds; Analysis 0003 option A for writers, HTTP for every reader).
4. **The read server connects as `qdt_reader`.** It has no writer and ingests nothing; running it with the
   reader DSN makes that a property of the database, not of the code. Tutorial 04 runs it that way.
5. **`deploy/qdt-db/roles.sql` and `python -m qdt_registry init` are the schema step.** The SQL creates the
   three roles with default privileges for tables the admin creates (writer `SELECT, INSERT` — rows are
   never updated, ADR 0026; reader `SELECT`); `init` (`Registry.init_server`) creates the tables as the
   admin and checks the DDL version. CI runs the same SQL against its ephemeral `qdt_test` so the roles
   file is exercised on every push, with one CI-only grant because the suite's tables are made by `qdt`.
6. **In L0 the reader is a SQLite file opened read-only** (`sqlite:///file:…?mode=ro&uri=true`) when no
   Postgres is configured: a write through it fails as a write through `qdt_reader` fails, so the tutorial
   proves the same thing on a laptop as in CI. With `QDT_TEST_PG_DSN` and `QDT_TEST_PG_READER_DSN` it is
   Postgres and the real role.

## Consequences
- Easier: Flight Deck needs no second build or flag for the database PC; a script needs one DSN and one
  URL; the roles are tested on every push rather than on the day the lab PC is set up.
- Harder: the read server's `/stream/replay` is a `POST` a strict reader might not expect — `/docs` on
  the read server shows exactly what exists; a reader that wants bytes must be able to reach the read
  server's port as well as (or instead of) 5432, which deliverable 6's IT ask must say.
- Must now: the step file's L0 row reworded (done); the runbook names the reader DSN for the read server
  (done); `docs/tutorials/README.md` lists tutorial 04 (done); the IT ask lists 8700/8765 for readers.

## Alternatives considered
- Strip `POST`/`DELETE` wholesale from the read server — rejected: it would strip replay, and Flight Deck's
  History could not open a record on the database PC, which is the demo.
- Flight Deck probes a command route to detect a read server — rejected: a 404 is not a contract;
  `/server` is one line and is generated into the client types.
- A `PayloadRef` with a URL, or `Registry.payload` fetching over HTTP itself — rejected for now: the
  registry client would grow an HTTP dependency for one method; the tutorial's two lines of `httpx`
  and a hash check are the whole of it. Revisit if a third consumer wants it.
- The read server as `qdt_writer` "because it is on the box anyway" — rejected: the property that it
  cannot write should not depend on which routes a build forgot to remove.
- A SQLite reader that merely lacks a store (no `mode=ro`) — rejected: it would not refuse a write, so
  L0 would prove less than CI.
