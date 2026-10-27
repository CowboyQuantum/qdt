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
  auth.py       # the command token (ADR 0074, 0082): token file, loopback test, the stand router's dependency; who sent a command
  state.py      # StandBook: the StandState in force (ADR 0075, 0085), its versions in the registry, the held point offered after a restart
  __main__.py   # python -m qdt_server --root <registry> [--host --port --stream-port --ui <dist> --read-only --tokens <file>] | --add-token <label>
```

## Rules
- Every request and response body is a schema object (`SweepDefinition`, `ExecutionPlan`, `Run`,
  `MeasurementRecord`, `MethodSpec`, `AnalysisResult`, `CalibrationNode`, `TuneUp`, `NodeOutcome`,
  `StandState`) or a list of them. No ad-hoc JSON shapes: the OpenAPI document is generated from them
  and the UI's client is generated from that (ADR 0034).
- The server never defines schema objects (that is `qdt-schemas`) and never computes an analysis itself
  (that is `qdt-analysis`): it compiles, executes, stores, serves.
- `GET /levels/state` (ADR 0057) reports every level-setting or level-sensing channel's setpoint, held level and readback (null where the instrument refuses the channel) from one live instrument set the `RunManager` builds once and keeps; on the simulator that set is separate from a run's seeded device.
- The `TuneUpManager` binds a node's inputs from the accepted outcomes before it, or from the held operating point for a binding with a `held` fallback (a retune, ADR 0062), and holds a node's `holds` outputs as the operating point when the node is accepted.
- Runs and tune-ups live in memory; records, results, node outcomes and stand state versions are the
  durable things. A server restart forgets runs and tune-ups, never what they produced: every record
  carries the operating point its sweep ran at, because the `RunManager` merges the held levels into
  each definition it compiles or runs.
- The stand state (ADR 0075, 0085) is versioned in the registry through `state.StandBook`: limits,
  couplings and the held operating point (`/levels`, ADR 0053). Every change writes the next version
  with who sent it (`auth.commander`: the token's label, or `local`) and why. Every level set, every
  compile and every queued run when it starts is checked against the limits in force and refused
  beyond them, never clamped (`qdt_lab.experiment.check_limits`). After a restart the held point is
  offered at `GET /levels/pending` and applied only by `POST /levels/pending/confirm`; until then
  nothing is held and no sweep inherits it.
- Step 4b wires the `simulated` backend only. Real drivers (Step 5) enter through `build_backends` with
  their factories; the API does not change. The simulated stand is `qdt_sim`'s double dot plus a
  simulated scope (`scope`, channel `scope1`, ADR 0047) whose record is a droop set by the run options
  `tau_s`, `droop_v`, `scope_noise_v`.
- A method is callable from the API only if it is in `catalogue.METHODS` with a `MethodSpec` whose
  parameters match the function's keyword arguments (the test pins this).
- Commands need a token off loopback (ADR 0074, 0082): every route on the `stand` router carries
  `auth.command_token`, which challenges any method but GET/HEAD/OPTIONS when the peer is not loopback
  and accepts `Authorization: Bearer <token>` with a token from `Settings.token_file` (`<root>/tokens`
  by default; one per line, a label after it; read on every command, so deleting a line revokes). Reads,
  `POST /stream/replay` (a read that happens to be a POST) and the CORS preflight are never challenged.
  A missing file refuses every command from elsewhere. Tests speak from loopback
  (`TestClient(app, client=LOOPBACK)`); the default peer `testclient` counts as another computer.
  Logins and roles are the hub's (ADR 0076).
- `--ui` (Settings.ui) serves a built Flight Deck as static files at `/`, mounted after every API route;
  the server knows nothing about the UI beyond that. `scripts/demo_control_path.py` builds and serves it.
