# qdt-server — package rules

The control path (ADR 0032, 0034): the one process that holds backends and a `Registry`, and exposes
an HTTP API for commands and queries beside the `Dataset` stream (`qdt_lab.stream.StreamServer`).
Flight Deck talks to this API and the stream only (rule 8).

## Layout
```
qdt_server/
  app.py        # create_app(settings) → FastAPI; lifespan starts the stream server; routes
  runs.py       # RunManager: queue → compile → execute on a backend → stream → record → ingest; abort; `Run` objects
  catalogue.py  # METHODS: MethodSpec per curated method + the callable; run_method()
  tuning.py     # run_node / run_tuneup (direct); TuneUpManager: tune-ups through the RunManager, TuneUp lifecycle, outcomes to the registry (ADR 0048–0050)
  __main__.py   # python -m qdt_server --root <registry> [--host --port --stream-port --ui <dist>]
```

## Rules
- Every request and response body is a schema object (`SweepDefinition`, `ExecutionPlan`, `Run`,
  `MeasurementRecord`, `MethodSpec`, `AnalysisResult`, `CalibrationNode`, `TuneUp`, `NodeOutcome`) or a
  list of them. No ad-hoc JSON shapes: the
  OpenAPI document is generated from them and the UI's client is generated from that (ADR 0034).
- The server never defines schema objects (that is `qdt-schemas`) and never computes an analysis itself
  (that is `qdt-analysis`): it compiles, executes, stores, serves.
- Runs, tune-ups and the held operating point (`/levels`, ADR 0053) live in memory; records, results and
  node outcomes are the durable things. A server restart forgets runs, tune-ups and the held levels,
  never what they produced: every record carries the operating point its sweep ran at, because the
  `RunManager` merges the held levels into each definition it compiles or runs.
- Step 4b wires the `simulated` backend only. Real drivers (Step 5) enter through `build_backends` with
  their factories; the API does not change. The simulated stand is `qdt_sim`'s double dot plus a
  simulated scope (`scope`, channel `scope1`, ADR 0047) whose record is a droop set by the run options
  `tau_s`, `droop_v`, `scope_noise_v`.
- A method is callable from the API only if it is in `catalogue.METHODS` with a `MethodSpec` whose
  parameters match the function's keyword arguments (the test pins this).
- No authentication in Step 4b (single machine). Multi-user and deployment are Step 7.
- `--ui` (Settings.ui) serves a built Flight Deck as static files at `/`, mounted after every API route;
  the server knows nothing about the UI beyond that. `scripts/demo_control_path.py` builds and serves it.
