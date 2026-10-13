# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4b — Control path → `docs/steps/04b-control-path.md` (Step 4 DONE, ADR 0033)
**Branch:** `step-4/close` (PR against `main` open; the human merges), then `step-4b/<short-name>`.
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
| from a fresh browser with only `qdt-server` running against the simulator: craft a sweep + pulse sequence, run, watch live, find the record, run a curated analysis, see overlays and output — e2e in CI and as a scripted demo | ✘ not started |
| `control.py` (`Run`, `MethodSpec`) frozen with ADR | ✘ not started |

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
**Human:** merge the Step 4 close PR.
**Then** Step 4b, first build session, on `step-4b/<short-name>`: ADR for the web framework and API
shape (proposal: FastAPI + uvicorn, REST for commands and queries, the existing WebSocket stream for
data, TS client generated from the OpenAPI document as the stream types are from JSON Schema); scaffold
`packages/qdt-server` as a workspace member (`python -m qdt_server --root <registry>`): stands/devices,
validate + compile a `SweepDefinition`, start a run against `SimulatedDevice` that streams through the
`StreamServer` and records into the registry, list runs/records, list methods, run a method, fetch
results; `control.py` (`Run`, `MethodSpec`) with fixtures and exports; API contract tests against the
simulator. Flight Deck editors and browser come in the following sessions.

## Decisions pending
- #10 surrogate DUT design (by Step 5 entry). Advisory treatment of the two wall-clock CI gates. Whether to
  fix the zero-clipping duplicate states in the dot model (ADR 0020 amendment, regenerates a fixture).
  Whether the diamond estimator should survive warm edges before the freeze (not required by the step).
