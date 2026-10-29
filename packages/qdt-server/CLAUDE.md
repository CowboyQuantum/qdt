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
  run_queue.py  # RunQueue: the stand's run queue (ADR 0075, 0086), kept in the cache; a worker runs one entry at a time through the RunManager
  __main__.py   # python -m qdt_server --root <registry> [--host --port --stream-port --ui <dist> --read-only --tokens <file>] | --add-token <label>
```

## Rules
- Every request and response body is a schema object (`SweepDefinition`, `ExecutionPlan`, `Run`,
  `MeasurementRecord`, `MethodSpec`, `AnalysisResult`, `CalibrationNode`, `TuneUp`, `NodeOutcome`,
  `StandState`, `RunRequest`, `QueuedRun`, `StandQueue`, `DeviceLayout`) or a list of them. No ad-hoc JSON shapes:
  the OpenAPI document is generated from them and the UI's client is generated from that (ADR 0034).
- The server never defines schema objects (that is `qdt-schemas`) and never computes an analysis itself
  (that is `qdt-analysis`): it compiles, executes, stores, serves.
- `GET /device/layout` (ADR 0089) serves `Settings.layout`, the device's gates seen from above for the Device widget: the simulated device's by default (`qdt_sim.scenarios.layout`), None with `--stand`, which answers 404. A real device's layout is site geometry and stays out of the repository (rule 7).
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
- The run queue (ADR 0075, 0086) is `run_queue.RunQueue`: entries in the registry cache's `run_queue`
  table, run one at a time through `RunManager.start` (so the limits are checked again when an entry
  starts) by a worker in the event loop; every `/queue` route is `async` so none races it. Move and
  remove apply to waiting entries, abort to the running one (409 otherwise). After a restart with
  entries waiting the queue is paused until a person resumes it; an entry running at the stop is
  recorded as aborted. `POST /runs` stays for scripts, the bench rows and tune-ups and shares the
  `RunManager`'s lock, so one run at a time holds for both. Tune-ups are not queue entries yet.
- Step 4b wires the `simulated` backend only. Real drivers (Step 5) enter through `build_backends` with
  their factories; the API does not change. The simulated stand is `qdt_sim`'s Phantom device (ADR 0088)
  plus a simulated scope (`scope`, channel `scope1`, ADR 0047) whose record is a droop set by the run
  options `tau_s`, `droop_v`, `scope_noise_v`. The device's run options are `seed` (the noise seed),
  `noise` and `device` (a committed device file; any other name fails the run). Its registry record
  carries Phantom's provenance (`qdt_sim.scenarios.provenance`). The server never imports Phantom and
  no route serves the device's truth.
- Tune-up windows are the stand's (ADR 0088): `Settings.nodes` maps a node id to the keyword windows its
  `qdt_tuning.TEMPLATES` constructor takes. The simulated stand's are `app.SIMULATED_NODES`, about the
  device's programmed point; a real stand (`--stand`) gives none, so its nodes keep the defaults.
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
