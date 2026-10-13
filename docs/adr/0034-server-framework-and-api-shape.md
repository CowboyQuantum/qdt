# 0034 — `qdt-server`: FastAPI over the schema objects, REST for commands and queries, the existing WebSocket for data

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4b

## Context
ADR 0032 inserted the control path before the drivers and left two decisions to the first build
session: the web framework and the API's wire shape. The constraints: every object the UI sends or
receives already exists as a pydantic model in `qdt-schemas` (rule 3; `FINISH_LINE.md`); the UI's types
are generated, never hand-written (ADR 0006); the `Dataset` stream and its WebSocket server exist and
are frozen (ADR 0010, 0015); `qdt-lab` never touches a database and `qdt-registry` never computes, so
the process that does both is new.

## Decision
`packages/qdt-server`, a workspace member, is that process. It is a FastAPI application whose request
and response bodies are the schema objects themselves (`SweepDefinition`, `ExecutionPlan`, `Run`,
`MeasurementRecord`, `MethodSpec`, `AnalysisResult`) or lists of them, plus three small request
envelopes (`RunRequest`, `MethodRequest`, `ReplayRequest`) and a `StreamInfo`. FastAPI is chosen because
it is pydantic-native: the models validate the bodies, and the generated OpenAPI document carries their
JSON Schema, from which the Flight Deck client is generated the way `src/schema/data.ts` is generated from
`data.schema.json`.

Commands and queries are REST over HTTP: `GET /stand`, `/devices`, `/stream`, `/methods`, `/runs`,
`/runs/{id}`, `/records`, `/records/{id}`, `/results`, `/results/{id}`; `POST /sweeps/compile` (returns
the plan or 400), `POST /runs` (202 with a queued `Run`; errors in compilation are 400 now, errors in
execution become a `failed` run), `POST /records/{id}/results` (runs a curated method synchronously,
stores the result and its output, 201), `POST /stream/replay` (publishes a stored record with its
overlays, or a result's output, on the stream). Data stays on the existing `StreamServer`, started in
the app's lifespan on its own port; a run is executed by feeding its `Source` to that server, which runs
the executor in a worker thread, and is recorded and ingested when the feed completes. One run at a time
per server in Step 4b. `Run`s are in-memory; a restart forgets runs, never records.

The `simulated` backend is the only one wired (`Settings.backends`); drivers enter through the same
factory in Step 5. No authentication (ADR 0032).

## Consequences
- Easier: no DTO layer. A schema change is visible in the API and in the generated client in the same
  commit; `qdt-server` has no schema of its own.
- Easier: the stream protocol and Flight Deck's sources are untouched; the UI's second channel is plain
  HTTP, testable with `TestClient`.
- Harder: the stream server keeps every message of a process lifetime in memory (ADR 0010's history);
  a long-running server with many runs and replays grows. A history cap or one stream per view is a
  later change to `StreamServer`, not to this API.
- Harder: `POST /records/{id}/results` is synchronous; a slow method blocks its request. Fine for the
  Step 4 methods on the maps the UI makes; a job queue is a later addition behind the same route.
- Must now: a method is callable from the API only through `catalogue.METHODS`, with a `MethodSpec`
  whose parameters match the function's keyword arguments (pinned by a test). `fastapi` and `uvicorn`
  are core dependencies of `qdt-server` only; no other package depends on them.

## Alternatives considered
- One WebSocket protocol for commands and data — rejected: commands want request/response semantics,
  status codes and OpenAPI; the data channel is already right as it is.
- gRPC or a custom RPC — rejected: the browser is the client and JSON Schema is already the shared type
  system.
- Flask or Django — rejected: neither validates bodies with the pydantic models the repo already has.
- A job queue (Celery, RQ) for runs — rejected for 4b: one simulated run at a time on one machine; the
  run manager's lock is enough and a queue would add a broker to deploy.
