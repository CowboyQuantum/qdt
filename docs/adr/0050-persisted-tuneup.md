# 0050 — The tune-up as a lifecycle object (`TuneUp`), outcomes persisted (`tuning_outcomes`, DDL v3), a topological order, the tune-up API and Flight Deck's DAG state

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 6 (adds to the control slice frozen by ADR 0036 and the registry's tables, ADR 0026; extends ADR 0048, 0049)

## Context
After ADR 0049 two nodes ran chained on the simulator, but only through a Python call: `run_tuneup`
took a list the caller had to order, kept its outcomes in memory, and nothing reached the stream, the
API or Flight Deck. Step 6's exit criterion is a multi-node tune-up that runs *unattended* against the
sim, and the finish line asks the UI to render tune-up state as a schema object it never stores. ADR
0048 deferred persisting outcomes until the DAG runner arrived. This is that runner.

The server already has the pattern: a `Run` is the in-memory lifecycle of one sweep, the
`MeasurementRecord` it produces is durable, and `RunManager` executes sweeps one at a time on the
stream. A tune-up is the same shape one level up: a `TuneUp` is the lifecycle, its `NodeOutcome`s are
durable, and each node's sweep is a `Run`.

## Decision
- **`TuneUp`** (control slice, additive beside `Run` and `MethodSpec`): the nodes in topological order,
  the outcomes so far, `state` (queued → running → completed | stopped | failed), `current_node`,
  `message`, timestamps, the run options as `attrs`. `completed` means every node accepted; `stopped`
  means a node was rejected or failed or a stop was requested (`message` says which); `failed` means the
  runner itself failed. It lives in the server's memory like `Run`; a restart forgets tune-ups, never
  outcomes.
- **`NodeOutcome` is persisted**: a `tuneup_id` field (additive), a `tuning_outcomes` table (append-only;
  indexes on tune-up, node, status; foreign keys to its record and result, both nullable since a failed
  node may have neither), `DDL_VERSION` 3 with an additive upgrade, `Registry.add_outcome`, `outcomes`,
  `outcome`, and outcomes in `sync` after results. `NodeOutcome` joins `migrations.PERSISTED`.
- **Order**: `qdt_tuning.order(nodes)` is a stable topological sort over `depends_on`; `run_tuneup` and the
  manager use it, so a caller may list nodes in any order. Cycles, strangers and repeated ids are errors.
- **`qdt_tuning.nodes.TEMPLATES`**: node id → constructor taking the stand's sequencer instrument id;
  what a server offers.
- **`TuneUpManager`** (`qdt_server.tuning`): `templates()` builds every template for the stand's
  sequencer; `start(nodes, options, scenario)` queues a `TuneUp` and runs it in the background, one at a
  time: for each node, bind its inputs from the accepted outcomes, start its sweep through the
  `RunManager` (so it streams to Flight Deck and is recorded like any run), wait for the run, then
  `analyse_and_decide` (the catalogue method, `add_result`, the rule, `add_outcome`); stop at the first
  outcome that is not accepted. `stop(tuneup_id)` ends it between nodes. A `SimScenario` in the request
  becomes the run options (seed, noise, model overrides) and tags the outcomes.
- **API**: `GET /nodes`, `POST /tuneups` (`node_ids`, `options`, `scenario`, `name`), `GET /tuneups`,
  `GET /tuneups/{id}`, `POST /tuneups/{id}/stop`, `GET /outcomes?tuneup_id=&node_id=&status=`,
  `GET /outcomes/{id}`. Every body is a schema object or a list of them (ADR 0034).
- **Flight Deck**: a Tune-up section in the control panel lists the nodes, starts a tune-up and polls
  its `TuneUp`, rendering the DAG state: each node with its status and message, the decided outputs of
  accepted nodes. The live map is the node's run on the stream, as today.

## Consequences
- Easier: the exit criterion's first half is met on the simulator: `POST /tuneups` with both nodes
  completes unattended, the outcomes are in the registry pointing at durable records and results, and
  the UI shows the state. The same request on a bench stand runs the same nodes.
- Easier: history is queryable: every outcome a device ever had, by node, by tune-up, by status, synced
  to the server with everything else.
- Harder: one tune-up at a time per server, and a stop takes effect between nodes (the node running now
  finishes). Parallel branches, retries and resuming a stopped tune-up are later.
- Harder: `TuneUp` is not persisted, so a crashed server loses which outcomes belonged together except
  through their shared `tuneup_id` on the stored outcomes. A `tuneups` table is a later additive change.
- Harder: `tuning_outcomes.result_id` references `analysis_results`, so an outcome can only be stored
  after its result; `analyse_and_decide` keeps that order.
- Must now: a new node template registers in `TEMPLATES` and lands with its `SimResult` fixture; a
  server whose stand has no sequencer offers no nodes (`GET /nodes` is empty) and refuses a tune-up.

## Alternatives considered
- Persisting `TuneUp` too — deferred: it changes state, and the registry is append-only; storing a
  terminal snapshot is possible later as a `tuneups` table, once something reads it.
- Running node sweeps directly in the manager (as `run_node` does) instead of through the `RunManager`
  — rejected: the stream and the live map are the point of a tune-up the human watches; the run path
  also gives abort and the same recording code.
- A graph request body (nodes with edges) — rejected: `depends_on` on the node is the edge, and the
  server orders; the request names templates.
- Stopping a tune-up by aborting the current run — deferred: a stop between nodes is clean and
  sufficient for now; the current run is still a valid record.
