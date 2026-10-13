# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4 — Analysis as a consumer → `docs/steps/04-analysis-overlays.md`
**Branch:** `step-4/analysis-overlays` (PR #10 against `main`; the human merges). Next session: a new
`step-4/<short-name>` from `main`.
**Last session:** 2026-10-13, session 13. Opened Step 4. The human decided the scenario ref (ADR 0029)
and, later in the session, to add a source–drain bias to the model now (ADR 0031). Built the
`modeling.py` slice, two `qdt-analysis` pipelines (charge transitions, Coulomb diamonds) with
injection–recovery in CI, the registry's `analyses` table with the first DDL migration (ADR 0030),
overlays on replay, Tutorial 03.

## Step 4 exit criteria
| Criterion | State |
|---|---|
| a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset | ◐ runs end to end in Python (Tutorial 03; the reference client receives the overlays); not yet seen in Flight Deck by a human |
| `modeling.py` slice (`FitModel`, `AnalysisResult`) frozen with ADR | ✘ defined (ADR 0029), not frozen; freeze after the Flight Deck demo |
| L0: injection–recovery on synthetic and `SimulatedDevice` data; `AnalysisResult` needs measurement ref + scenario ref | ✔ `packages/qdt-analysis/tests`, `packages/qdt-schemas/tests/test_modeling.py` |

Deliverables: `qdt-analysis` pure functions ✔ (charge transitions; Coulomb diamonds with the
detection/estimation split); Flight Deck overlay layer ✔ (the Step 1 layer, unchanged, draws lines,
markers and regions in data coordinates).

## Done
- Steps 0–3 DONE. ADR 0001–0031. Frozen: `Dataset` contract (0015), protocols (0021), stand/activity/pulse
  (0022), identity/envelope/`qdt-hdf5-v1` (0028). All at `schema_version` 1.
- **Modeling slice (ADR 0029):** `qdt_schemas.modeling`: `FitModel`, `MeasurementRef` (dataset, variable,
  optional record), `ScenarioRef` (`simulation` | `synthetic`, name, seed, scalar parameters),
  `AnalysisResult` (both legs mandatory; annotations must decorate the measured Dataset). In `PERSISTED`
  with a fixture; `records.schema.json` regenerated.
- **qdt-sim:** `DoubleDotModel.ground_state` / `transition_map` (honeycomb truth); the sensor is a biased
  SET (`sensor_charging_ev`, `sensor_bias_v`, `sensor_current(phi, v_sd)`, `diamond_edges`; ADR 0031);
  `SimulatedDevice` has a `bias` channel role; the default stand declares `bias` and `bias_pulse`.
  `scenarios.SCENARIOS` = stability, stability_fixture, diamonds; `resolve(ref)` rebuilds sweep, stand and
  seeded device, routing parameters by name (device options, scalar model fields, `<axis>_start/_stop`
  ranges, sweep arguments). The 24×32 stability fixture was regenerated (model changed, ~1 %).
- **qdt-analysis:** `charge_transitions` (robust scale → smooth → gradient ridges with a noise floor from
  a median-filter residual → orientation families → 8-connected runs → weighted TLS segments, collinear
  adjacent runs merged) and `coulomb_diamonds` (same edge detection; then zero-bias crossings clustered
  into degeneracy points, period, median slopes, apexes, `E_c = e·V_apex`, lever arm `E_c/period`; edges,
  points and complete diamonds as annotations). `recovery` scores a result against a truth mask.
  Injection–recovery in CI: synthetic lines (p, r = 1.0); noise-free honeycomb (p > 0.95, r > 0.9 at
  1.5 px); noisy default device (p > 0.85, r > 0.8 at 2 px); synthetic diamonds and simulated sensor
  diamonds with a cold sensor (`sensor_width_v` 0.01): E_c within 5 %, period 3 %, lever arm and slopes 8 %.
- **Registry (ADR 0030):** `analyses` table, `DDL_VERSION` 2, `qdt_registry.migrations` (`STEPS`,
  `migrate`; DDL-1 databases upgrade on open; newer refused). `Registry.record_analysis`,
  `analyses(record_id)`, `analysis(id)`; `sync` uploads analyses after records. `python -m qdt_registry
  serve` streams a record's analysis annotations as overlays (`PayloadSource(..., annotations=)`).
- **Tutorial 03** (`docs/tutorials/test_03_analysis.py`): record → find → analyse → keep → replay with
  overlays → score against the scenario's truth.
- 257 Python tests (+ Postgres-parametrized when `QDT_TEST_PG_DSN` is set; CI sets it), 26 Flight Deck
  unit tests, 2 e2e. Flight Deck source unchanged this session (`data.schema.json` did not change).

## In flight
- Nothing uncommitted. PR #10 (`step-4/analysis-overlays` → `main`) open.

## Known broken / not yet real
- The diamond estimator needs sharp edges: at the stability default sensor width (40 mV, kT_s ≈ 80 µeV)
  the thermal tails of neighbouring edges overlap into blobs around the apexes and E_c comes out ~30 %
  low on 64×64. Name a colder sensor in the scenario ref (as the test does) or add non-maximum
  suppression / a direct model fit later (ADR 0031).
- Symmetric leads only: diamonds are symmetric; E_c read from either apex.
- Flight Deck draws every annotation in one colour with its label; analysis lines are labelled `f0`/`f1`
  (orientation family), degeneracy points `g<k>`, diamonds `E_c … meV`. Per-kind colour is polish.
- Postgres suite not run locally this session: `docker` is not on PATH in this shell. CI runs it. Local:
  `docker compose -f deploy/registry.compose.yml up -d`, then
  `QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test` (use `127.0.0.1`, not `localhost`).
  A Step 3 Postgres server (DDL 1) will be migrated to DDL 2 by the first new client that connects.
- Two wall-clock-bound CI gates flake on shared runners (Flight Deck renderer bench rendered rate;
  `test_wire_path_keeps_design_target_line_rate`). Advisory treatment still undecided (cf. ADR 0014).
- Carried over: model physics gaps (ADR 0020: no tunnel coupling, spin, valley, DQD transport); waveform
  protocols frozen without a call site (ADR 0021); QUA emitter and real drivers (Step 5); `FINISH_LINE.md`
  TODO (human); `BENCH.md` skeleton; DUT #10.
- Windows: `pnpm` is not on PATH; use `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:** merge PR #10, check CI (Postgres job included). See the overlays: run Tutorial 03's steps 1–3
against `~/.qdt/registry` (point `Registry(...)` there), then `uv run python -m qdt_registry serve
<record_id>` and `corepack pnpm dev` in `apps/flightdeck`. For diamonds, do the same with
`ScenarioRef(kind="simulation", name="diamonds", seed=…, parameters={"sensor_width_v": 0.01})` and
`coulomb_diamonds`.
**Then** on `step-4/<short-name>`: (1) freeze `modeling.py` with an ADR once the human has seen the
overlays (review field by field against `charge_transitions`, `coulomb_diamonds`,
`Registry.record_analysis`, Tutorial 03, as ADR 0028 did); (2) mark the step DONE in
`docs/steps/04-analysis-overlays.md` and `docs/steps/README.md`; (3) open Step 5 (`docs/steps/05-…`).

## Decisions pending
- #10 surrogate DUT by Step 5 entry. Advisory treatment of the two wall-clock CI gates. What a *live*
  measurement's `ScenarioRef` is (Step 5, ADR 0029). Whether the diamond estimator should survive warm
  edges before the freeze (STATUS: not required by the step).
