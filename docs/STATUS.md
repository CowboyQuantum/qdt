# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4b — Control path → `docs/steps/04b-control-path.md` (Step 4 DONE, ADR 0033)
**Branch:** `step-4b/view-options` (PR against `main` open; the human merges). PRs #14–#18 merged.
**Last session:** 2026-10-13, session 13. Two sessions built Step 4 in parallel; the human merged PR #9
(`step-4/analysis`: record + method provenance, lattice estimation, ADR 0029) and closed PR #10. This
session then ported onto `main` what #9 lacked: a source–drain bias across the sensor SET, the
`diamonds` sweep, the Coulomb diamond method with injection–recovery, and a recovery scorer (ADR 0030).
`ScenarioRef` (PR #10's reading of the scenario ref) was dropped per the human's choice. After seeing the
overlays in Flight Deck the human reviewed the analysis objects and decided: curated methods only,
multi-record analyses deferred, and results may carry arrays. Built as ADR 0031: an output is a Dataset
in a payload referenced from the result.

## Step 4 exit criteria — all met (DONE, ADR 0033)
| Criterion | State |
|---|---|
| a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset | ✔ seen by the human in Flight Deck (transitions); diamonds and outputs via `scripts/demo_analysis.py --diamonds` and `serve --output` |
| `modeling.py` slice frozen with ADR | ✔ ADR 0033 |
| L0: injection–recovery on synthetic and `SimulatedDevice` data; both provenance halves mandatory | ✔ |

## Step 4b exit criteria
| Criterion | State |
|---|---|
| from a fresh browser with only `qdt-server` running against the simulator: craft a sweep + pulse sequence, run, watch live, find the record, run a curated analysis, see overlays and output — e2e in CI and as a scripted demo | ◐ `apps/flightdeck/e2e/control.test.ts` does it in Chrome against a spawned server (form → run → live map → record → analysis → overlays painted). The pulse sequence is the one-step template, not yet edited; the scripted demo is "start the server, open Flight Deck" |
| `control.py` (`Run`, `MethodSpec`) frozen with ADR | ✘ defined (ADR 0032/0034), not frozen |

## Done
- Steps 0–4 DONE. ADR 0001–0033. Frozen: `Dataset` contract (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; `ExecutionPlan` v2 by 0031), identity/envelope/`qdt-hdf5-v1` (0028),
  modeling (0033).
- **Step 4 (ADR 0029):** `qdt_schemas.modeling` (`FitModel`, `Estimate`, `AnalysisResult`; persisted,
  v1 fixture). `qdt_analysis.transitions.detect_transitions`: detection (`detect_segments`: threshold +
  NMS + direction families + connected runs → line overlays) separate from estimation (charge lattice
  from the gradient-magnitude spectrum). `DoubleDotModel.charge_lattice` is the injection truth.
  Registry `analysis_results` table (`DDL_VERSION` 2, additive upgrade from 1), `add_result`/`results`,
  synced. `serve` publishes stored overlays. Tutorial 03.
- **Step 4 (ADR 0030):** the sensor is a biased SET (`sensor_charging_ev`, `sensor_bias_v`,
  `sensor_current(phi, v_sd)`, `diamond_edges`); `SimulatedDevice` has a `bias` channel role (DC level
  starts at `sensor_bias_v`; pulses add); the default stand declares `bias` and `bias_pulse`;
  `scenarios.diamonds` (DC-only sweep, sensed current); `default_device(model=...)` for a replaced model.
  `qdt_analysis.diamonds.detect_diamonds`: edges via `detect_segments` in pixel-space families, then
  degeneracy points (length-weighted crossings with each family's median slope), period, apexes,
  `E_c = e·V_apex`, lever arm, as `Estimate`s; edges, points and diamonds as overlays; `failed` without a
  complete diamond. `qdt_analysis.recovery` scores line overlays against a truth mask. The 24×32
  stability fixture was regenerated (model changed, ~1 % at the default bias).
- **Step 4 (ADR 0031):** `AnalysisResult.output: PayloadRef | None`; a method returns
  `Analysis(result, output)` with the output as an in-memory `Payload` whose Dataset has
  `source.kind="analysis"` (new kind: `Dataset` v2, `ExecutionPlan` v2, identity migrations, v1 fixtures
  kept, exports and Flight Deck types regenerated; the wire decoder upgrades on read).
  `Registry.add_result(result, output)` writes `analysis/<YYYY>/<MM>/<result_id>.h5`, fills the ref and
  returns the stored result; `Registry.result`/`output`; `sync` uploads outputs; `serve --output
  <result_id>` streams one to Flight Deck. Both methods output their detection map (gradient + edges).
- **Step 4b session 1 (ADR 0034):** `qdt_schemas.control` (`ParameterSpec`, `EstimateSpec`, `MethodSpec`
  with `resolve`/`fit_model`; `Run` with a checked lifecycle). `packages/qdt-server` (FastAPI; `python -m
  qdt_server --root --port --stream-port`): `GET /stand /devices /stream /methods /runs /runs/{id}
  /records /records/{id} /results /results/{id}`, `POST /sweeps/compile` (plan or 400), `POST /runs`
  (202, queued `Run`; executes on the simulator through the `StreamServer`, records, ingests; one at a
  time), `POST /records/{id}/results` (curated method by `MethodSpec`, stores result + output, 201),
  `POST /stream/replay` (record with overlays, or a result's output). `catalogue.METHODS` pins each spec
  to its function's signature. `fastapi`/`uvicorn` are `qdt-server` deps only; `httpx` dev.
- **Step 4b session 2:** `scripts/export_openapi.py` → `packages/qdt-server/exports/openapi.json`
  (drift-checked in `check_all`); Flight Deck `pnpm gen:api` → `src/schema/api.ts` (drift-checked in CI);
  `src/api/client.ts` (typed fetch client, `?api=`); `src/control/sweeps.ts` (stage and DC sweep
  builders from a form; stand channel classification), `src/control/methods.ts` (MethodSpec → defaults,
  parse, check, overrides), `src/control/panel.ts` (craft/run/runs/records/analysis UI); every Dataset
  on the stream selectable (`#datasets`, newest shown first); `e2e/control.test.ts`.
- **Flight Deck view options (session 2b):** client-side transforms (raw, derivative along either axis,
  gradient magnitude; per index step, NaN-aware), a swap-axes toggle, and axis labels with units and
  extents drawn on the overlay. The plain view keeps the dirty-row live path the bench measures; a view
  option recomputes the display map client-side with no round trip (FINISH_LINE row 2).
- 267 Python tests (+5 Postgres-parametrized with `QDT_TEST_PG_DSN`), 41 Flight Deck unit tests, 3 e2e.

## In flight
- Nothing uncommitted. PR `step-4/result-output` → `main` open. Remote branches `step-4/analysis`,
  `step-4/diamonds` (merged) and `step-4/analysis-overlays` (PR #10, closed) await the human's pruning.

## Known broken / not yet real
- The diamond estimator needs sharp edges: at the stability default sensor width (40 mV, kT_s ≈ 80 µeV)
  the thermal tails of neighbouring edges overlap into blobs around the apexes and E_c comes out ~30 %
  low on 64×64. Use a cold sensor (`sensor_width_v` 0.01, as the test and the demo do) or add a direct
  model fit later (ADR 0030). Symmetric leads only.
- Lattice estimate needs a periodic window: the empty-dot corner biases cross terms ~6 % (tests use an
  occupied window). Strong tunnel coupling / nonlinear lever arms will need a new method version.
- `DoubleDotModel.energies` clips occupations at 0, creating duplicate states that slightly bias Boltzmann
  weights (~kT·ln 5 near empty dots, ≈0.1 px). Fixing it changes the committed sim fixture: ADR-level (0020).
- Flight Deck draws overlays in one colour with their labels; no per-family colour, no toggle.
- Postgres suite not run locally this session: `docker` is not on PATH in this shell. CI runs it. Local:
  `docker compose -f deploy/registry.compose.yml up -d`;
  `QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test` (`127.0.0.1`, not `localhost`).
- Two wall-clock-bound CI gates flake on shared runners (renderer bench rate; stream line-rate test).
  Decide advisory treatment (cf. ADR 0014).
- Carried over: model physics gaps (ADR 0020: no tunnel coupling, spin, valley, DQD transport); waveform
  protocols frozen without a call site (ADR 0021); QUA emitter and real drivers (Step 5); server payload
  store is a directory (ADR 0026); `FINISH_LINE.md` TODO (human); `BENCH.md` skeleton; DUT #10.
  Windows: `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:** merge the PR; then the demo: `uv run python -m qdt_server`, `corepack pnpm dev` in
`apps/flightdeck`, open the URL. The panel on the right: pick channels, set ranges, "run" (the map
draws live), the record appears under Records, "analyse" → pick a method → "run analysis" → "show
overlays". For diamonds: kind "DC", outer `SG` −0.2…0.2, inner `bias` −0.0015…0.0015 (name `V_sd`),
options `{"seed": 1, "noise": false, "sensor_width_v": 0.01}`, method "Coulomb diamonds".
**Then** Step 4b session 3: the pulse-sequence editor (edit the stage's `PulseSequence` body: steps,
ramps, waits, measures, symbols bound to axes) with its own unit tests; 1-D sweeps in the panel; a
`--demo` entry; then freeze `control.py` by ADR and close 4b. Step 5 (drivers) follows.

## Direction recorded (human, 2026-10-13)
- The end state is a web app: users run **curated** analyses from Flight Deck; no method authoring in
  the browser. Multi-record analyses deferred. Results may carry arrays as Datasets (ADR 0031).
- **The control path comes before the drivers** (ADR 0032): Step 4b, `docs/steps/04b-control-path.md`.
  `packages/qdt-server` (HTTP API beside the stream; simulated backend only), Flight Deck sweep and
  pulse-sequence editors, run panel, records browser, analysis panel; `control.py` (`Run`,
  `MethodSpec`). Exit: a fresh browser + the server does the whole loop on the simulator.

## Decisions pending
- #10 surrogate DUT design (by Step 5 entry). Advisory treatment of the two wall-clock CI gates. Whether to
  fix the zero-clipping duplicate states in the dot model (ADR 0020 amendment, regenerates a fixture).
  Whether the diamond estimator should survive warm edges before the freeze (not required by the step).
