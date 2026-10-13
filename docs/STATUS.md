# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4 — Analysis as a consumer → `docs/steps/04-analysis-overlays.md`
**Branch:** `step-4/result-output` (PR against `main` open; the human merges). PR #11 (diamonds) merged.
**Last session:** 2026-10-13, session 13. Two sessions built Step 4 in parallel; the human merged PR #9
(`step-4/analysis`: record + method provenance, lattice estimation, ADR 0029) and closed PR #10. This
session then ported onto `main` what #9 lacked: a source–drain bias across the sensor SET, the
`diamonds` sweep, the Coulomb diamond method with injection–recovery, and a recovery scorer (ADR 0030).
`ScenarioRef` (PR #10's reading of the scenario ref) was dropped per the human's choice. After seeing the
overlays in Flight Deck the human reviewed the analysis objects and decided: curated methods only,
multi-record analyses deferred, and results may carry arrays. Built as ADR 0031: an output is a Dataset
in a payload referenced from the result.

## Step 4 exit criteria
| Criterion | State |
|---|---|
| a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset | ✔ query → `detect_transitions` / `detect_diamonds` → `Registry.add_result` → `serve` delivers the overlays (reference client, Tutorial 03; `scripts/demo_analysis.py [--diamonds]`). **Human to eyeball in Flight Deck** |
| `modeling.py` slice (`FitModel`, `Estimate`, `AnalysisResult`) frozen with ADR | ✘ objects complete; freeze ADR at exit, after the human has seen the overlay |
| L0: injection–recovery on synthetic and `SimulatedDevice` data | ✔ lattices (±cross terms) to 2 %; noisy sweeps: diagonal 2 %, cross ratios ±0.02; diamonds: period 3 %, E_c 5 %, lever arm and slopes 8 %, edges p > 0.9 / r > 0.85 at 2 px |
| L0: `AnalysisResult` without measurement ref or method ref fails validation | ✔ `test_modeling.py` |

Deliverables: `qdt-analysis` pure functions ✔ (charge transitions with lattice estimation; Coulomb
diamonds with the detection/estimation split); Flight Deck overlay layer ✔ (the Step 1 layer, unchanged,
draws lines, markers and regions in data coordinates).

## Done
- Steps 0–3 DONE. ADR 0001–0030. Frozen: `Dataset` contract (0015), protocols (0021), stand/activity/pulse
  (0022), identity/envelope/`qdt-hdf5-v1` (0028).
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
- 247 Python tests (+5 Postgres-parametrized with `QDT_TEST_PG_DSN`), 26 Flight Deck unit tests, 2 e2e.
  Flight Deck source unchanged except the generated `src/schema/data.ts`.

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
**Human:** merge the PR; then look at the overlays:
`uv run python scripts/demo_analysis.py` (transitions) and `uv run python scripts/demo_analysis.py
--diamonds` (each prints a record id), then `uv run python -m qdt_registry serve <record_id>` and
`corepack pnpm dev` in `apps/flightdeck`. Transition segments should lie on the honeycomb edges; the
diamond edges, `g<k>` markers and `E_c` regions on the sensor's diamonds. The demo also prints
`serve --output <result_id>`: the detection map the method worked on, as a Dataset of its own.
**Then** close Step 4: review `FitModel`/`Estimate`/`AnalysisResult` against what both methods, the
registry and Tutorial 03 used; write the freeze ADR; mark Step 4 DONE (`docs/steps/04-…`, `README.md`);
delete `step-4/analysis-overlays`; open Step 5 (instrument drivers) and settle #10 (surrogate DUT) with
the human at Step 5 entry.

## Direction recorded (ADR 0031, human, 2026-10-13)
- The end state is a web app: users run **curated** analyses from Flight Deck; no method authoring in
  the browser. Multi-record analyses deferred. Results may carry arrays as Datasets.
- Not yet on the roadmap: the backend service that lets the UI query the registry, run a method, and
  craft/compile/run a sweep (the "control path"). Today Flight Deck has one channel in (the stream) and
  one planned channel out (click-to-set, Step 6). A method catalogue (name, version, parameter schema
  for forms, applicable shapes, promised estimates) enters with that service. Needs a step and a
  `FINISH_LINE.md` row; proposed to the human.

## Decisions pending
- #10 surrogate DUT design (by Step 5 entry). Advisory treatment of the two wall-clock CI gates. Whether to
  fix the zero-clipping duplicate states in the dot model (ADR 0020 amendment, regenerates a fixture).
  Whether the diamond estimator should survive warm edges before the freeze (not required by the step).
