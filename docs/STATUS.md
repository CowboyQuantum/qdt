# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4 — Analysis as a consumer → `docs/steps/04-analysis-overlays.md`
**Branch:** `step-4/analysis-overlays` (PR against `main`; the human merges). Next session: continue on a
new `step-4/<short-name>` from `main`.
**Last session:** 2026-10-13, session 13. Opened Step 4. The human decided the scenario ref (ADR 0029).
Built the `modeling.py` slice, the first `qdt-analysis` detector with injection–recovery in CI, the
registry's `analyses` table with the first DDL migration (ADR 0030), overlays on replay, Tutorial 03.

## Step 4 exit criteria
| Criterion | State |
|---|---|
| a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset | ◐ runs end to end in Python (Tutorial 03; reference client receives the overlays); not yet seen in Flight Deck by a human |
| `modeling.py` slice (`FitModel`, `AnalysisResult`) frozen with ADR | ✘ defined (ADR 0029), not frozen; freeze after the Flight Deck demo |
| L0: injection–recovery on synthetic and `SimulatedDevice` data; `AnalysisResult` needs measurement ref + scenario ref | ✔ `packages/qdt-analysis/tests`, `packages/qdt-schemas/tests/test_modeling.py` |

## Done
- Steps 0–3 DONE. ADR 0001–0030. Frozen: `Dataset` contract (0015), protocols (0021), stand/activity/pulse
  (0022), identity/envelope/`qdt-hdf5-v1` (0028). All at `schema_version` 1.
- **Modeling slice (Step 4, ADR 0029):** `qdt_schemas.modeling`: `FitModel`, `MeasurementRef` (dataset,
  variable, optional record), `ScenarioRef` (`simulation` | `synthetic`, name, seed, scalar parameters),
  `AnalysisResult` (both legs mandatory; annotations must decorate the measured Dataset). In `PERSISTED`
  with a fixture; `records.schema.json` regenerated. `qdt_sim.scenarios.resolve(ref)` rebuilds sweep,
  stand and seeded device from a ref; `DoubleDotModel.ground_state` / `transition_map` give the truth.
- **qdt-analysis:** `charge_transitions(dataset, arrays, scenario, record_id=..., **params)` →
  `AnalysisResult` of line annotations. Stages: `detect` (robust scale, smooth, gradient ridges with a
  noise floor from a median-filter residual, orientation families, 8-connected runs) and `estimate`
  (weighted TLS segment per run; collinear, adjacent runs merged). `recovery` scores a result against a
  truth mask (precision/recall in pixels). Injection–recovery passes on synthetic lines (p, r = 1.0),
  on a noise-free `SimulatedDevice` honeycomb (p > 0.95, r > 0.9 at 1.5 px) and on the noisy default
  device (p > 0.85, r > 0.8 at 2 px), 64×64 window P1, P2 ∈ [−0.02, 0.06] V.
- **Registry (ADR 0030):** `analyses` table, `DDL_VERSION` 2, `qdt_registry.migrations` (`STEPS`,
  `migrate`; a DDL-1 database upgrades on open; a newer one is refused). `Registry.record_analysis`,
  `analyses(record_id)`, `analysis(id)`; `sync` uploads analyses after records. `python -m qdt_registry
  serve` streams a record's analysis annotations as overlays (`PayloadSource(..., annotations=)`).
- **Tutorial 03** (`docs/tutorials/test_03_analysis.py`): record → find → analyse → keep → replay with
  overlays → score against the scenario's truth.
- 252 Python tests (+ Postgres-parametrized when `QDT_TEST_PG_DSN` is set; CI sets it), 26 Flight Deck
  unit tests, 2 e2e. Flight Deck source unchanged this session (the Step 1 overlay draws the results;
  `data.schema.json` did not change).

## In flight
- Nothing uncommitted. PR (`step-4/analysis-overlays` → `main`) open.

## Known broken / not yet real
- **Coulomb diamond pipeline** (Step 4 deliverable) not started: the dot model has no source–drain bias
  axis (ADR 0020 gaps), so there is nothing simulated to detect diamonds on. Decision pending below.
- Flight Deck draws every annotation in one colour with its label; analysis lines are labelled `f0`/`f1`
  (orientation family). Per-family colour or an analysis legend is polish, not a contract change.
- Postgres suite not run locally this session: `docker` is not on PATH in this shell. CI runs it. Local:
  `docker compose -f deploy/registry.compose.yml up -d`, then
  `QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test` (use `127.0.0.1`, not `localhost`).
  A Step 3 Postgres server (DDL 1) will be migrated to DDL 2 by the first new client that connects.
- Two wall-clock-bound CI gates flake on shared runners (Flight Deck renderer bench rendered rate;
  `test_wire_path_keeps_design_target_line_rate`). Advisory treatment still undecided (cf. ADR 0014).
- Carried over: model physics gaps (ADR 0020); waveform protocols frozen without a call site (ADR 0021);
  QUA emitter and real drivers (Step 5); `FINISH_LINE.md` TODO (human); `BENCH.md` skeleton; DUT #10.
- Windows: `pnpm` is not on PATH; use `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:** merge the PR, check CI (Postgres job included). See the overlays: run Tutorial 03's steps 1–3
against `~/.qdt/registry` (or `uv run python docs/tutorials/test_03_analysis.py` and point
`Registry(...)` at `~/.qdt/registry`), then `uv run python -m qdt_registry serve <record_id>` and
`corepack pnpm dev` in `apps/flightdeck`. Decide the Coulomb diamond question below.
**Then** on `step-4/<short-name>`: (1) freeze `modeling.py` with an ADR once the human has seen the
overlay (review field by field against `charge_transitions`, `Registry.record_analysis`, Tutorial 03,
as ADR 0028 did); (2) per the decision, either add a bias axis to `qdt-sim` (ADR; `SimulatedDevice`
needs a bias channel role) and a diamond detector/estimator, or defer diamonds to Step 6 and amend the
step file; (3) mark the step DONE in `docs/steps/04-analysis-overlays.md` and `docs/steps/README.md`.

## Decisions pending
- Coulomb diamonds in Step 4: add a source–drain bias to the model now, or defer to Step 6 (the step
  file lists diamonds as a deliverable; the model cannot produce them). #10 surrogate DUT by Step 5 entry.
  Advisory treatment of the two wall-clock CI gates. What a *live* measurement's `ScenarioRef` is (Step 5,
  ADR 0029).
