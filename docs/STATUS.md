# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4 — Analysis as a consumer → `docs/steps/04-analysis-overlays.md`
**Branch:** `step-4/analysis` (PR against `main` open; the human merges).
**Last session:** 2026-10-13, session (12, continued after the PR #8 merge). Scenario ref decided (= the
analysis method, human); built `modeling.py`, `qdt_analysis.transitions`, stored results in the registry,
overlays through `serve`, Tutorial 03 (ADR 0029).

## Step 4 exit criteria
| Criterion | State |
|---|---|
| a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset | ✔ query → `detect_transitions` → `Registry.add_result` → `serve` delivers 56 overlays (reference client, Tutorial 03). **Human to eyeball in Flight Deck** |
| `modeling.py` slice (`FitModel`, `Estimate`, `AnalysisResult`) frozen with ADR | ✘ objects complete; freeze ADR at exit, after the human has seen the overlay |
| L0: injection–recovery on synthetic and `SimulatedDevice` data | ✔ synthetic lattices (±cross terms) to 2%; noisy sweeps: diagonal 2%, cross ratios ±0.02 |
| L0: `AnalysisResult` without measurement ref or method ref fails validation | ✔ `test_modeling.py` |

## Done
- Steps 0–3 DONE. ADR 0001–0029. Frozen: `Dataset` contract (0015), protocols (0021), stand/activity/pulse
  (0022), identity/envelope/`qdt-hdf5-v1` (0028).
- **Step 4 so far (ADR 0029):** `qdt_schemas.modeling` (`FitModel`, `Estimate`, `AnalysisResult`; persisted,
  v1 fixture). `qdt_analysis.transitions.detect_transitions`: detection (threshold + NMS + connected
  segments → line overlays) separate from estimation (charge lattice from the gradient-magnitude spectrum:
  `a_/b_per_volt_row/col`, `cross_ratio_a/b`). `DoubleDotModel.charge_lattice` is the injection truth.
  Registry `analysis_results` table (`DDL_VERSION` 2, additive upgrade from 1), `add_result`/`results`,
  synced. `serve` publishes stored overlays. `scripts/demo_analysis.py`. Tutorial 03.
- 235 Python tests (+4 Postgres-parametrized with `QDT_TEST_PG_DSN`), 26 Flight Deck unit tests, 2 e2e.

## In flight
- Nothing uncommitted. PR `step-4/analysis` → `main` open.

## Known broken / not yet real
- Lattice estimate needs a periodic window: the empty-dot corner biases cross terms ~6% (tests use an
  occupied window). Strong tunnel coupling / nonlinear lever arms will need a new method version.
- `DoubleDotModel.energies` clips occupations at 0, creating duplicate states that slightly bias Boltzmann
  weights (~kT·ln 5 near empty dots, ≈0.1 px). Fixing it changes the committed sim fixture: ADR-level (0020).
- Flight Deck draws overlays as plain lines; no per-family colour, no toggle.
- Local Postgres: `docker compose -f deploy/registry.compose.yml up -d`;
  `QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test` (`127.0.0.1`, not `localhost`).
- Two wall-clock-bound CI gates flake on shared runners (renderer bench rate; stream line-rate test).
  Decide advisory treatment (cf. ADR 0014).
- Carried over: waveform protocols frozen without a call site (ADR 0021); QUA emitter and real drivers
  (Step 5); server payload store is a directory (ADR 0026); `FINISH_LINE.md` TODO (human); `BENCH.md`
  skeleton; DUT #10. Windows: `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:** merge the PR; then look at the overlay:
`uv run python scripts/demo_analysis.py` (prints a record id), then
`uv run python -m qdt_registry serve <record_id>` and `corepack pnpm dev` in `apps/flightdeck`. The
transition segments should lie on the honeycomb edges.
**Then** close Step 4: review `FitModel`/`Estimate`/`AnalysisResult` against what the detector, registry
and tutorial used; write the freeze ADR; mark Step 4 DONE; open Step 5 (instrument drivers) and settle
#10 (surrogate DUT) with the human at Step 5 entry.

## Decisions pending
- #10 surrogate DUT design (by Step 5 entry). Advisory treatment of the two wall-clock CI gates. Whether to
  fix the zero-clipping duplicate states in the dot model (ADR 0020 amendment, regenerates a fixture).
