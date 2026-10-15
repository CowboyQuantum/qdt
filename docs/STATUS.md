# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6 — Closed-loop tuning → `docs/steps/06-closed-loop-tuning.md` (IN PROGRESS, opened 2026-10-15).
**Branch:** `step-6/modeling-slice` (PR against `main`; the human merges). PRs #25–#42 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 2 (not at the bench). **The schema slice and the first node**
(ADR 0048). `modeling.py` gains, beside the frozen three, `SimScenario` (model overrides, seed, noise; the
truth derived by `qdt-sim`), `DecisionRule`, `CalibrationNode` (experiment + method + rule, as data, in
logical channel names), `NodeOutcome` (record, result, verdict, decided quantities) and `SimResult` (a
committed outcome with the truth). A new pure package **`qdt-tuning`** holds nodes and curated decision
rules (`RULES`, `decision_rule`, `apply`); `qdt-sim` realizes a scenario (`model_for`, `device_for`,
`lattice_truth`); **`qdt_server.tuning.run_node`** runs one node through the user's run path (compile,
execute, record, ingest, catalogue method, `add_result`) and applies the rule. The first node,
**`charge-lattice`** (stability diagram → `detect_transitions` → `virtual_gates`), is accepted on the default
scenario in 0.7 s: lattice within 0.6 % (diagonal) and 2.3 % (cross terms) of the model, virtual-gate
matrix `M = L⁻¹·diag(diag L)` within 0.007; two `SimResult` fixtures (`charge_lattice_default`, `_quiet`)
committed and reproduced in CI; a noisy empty-dot window is a `failed` outcome with its record kept.

## Step 6 exit criteria (from the step file)
| Criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | ◐ one node runs and decides; no DAG runner, no second node yet |
| first L3 contact as confirmation, not discovery | not started |

## Done
- **Steps 0–5 DONE.** ADR 0001–0048. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038, 0047), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033; Step 6 objects added beside it by 0048), control (0036; amended additively by 0046).
- **Step 6 so far:** the modeling objects; `qdt-tuning` (pure; `check_imports.py` enforces schemas-only);
  `run_node`; the `charge-lattice` node with its rule; scenario realization in `qdt-sim`;
  `scripts/make_tuning_fixtures.py`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis` (four curated methods),
  `qdt-tuning`, `qdt-server` (control path + node runner), `apps/flightdeck`.
- 368 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 71 unit tests and 5 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/modeling-slice` awaits the human.

## Known broken / not yet real
- **`detect_transitions` reports `ok` on a noiseless, nearly constant map** (the empty-dot window with
  noise off): a degenerate lattice with equal diagonals and zero cross terms. The relative gradient
  threshold finds the map's tiny ripple. A method fix is a `VERSION` bump (ADR 0029); until then the
  rule accepts it (it is a plausible lattice by its tests) and only the noisy case fails honestly.
- **Node outcomes are not persisted** (ADR 0048): a tune-up's history lives in memory until a
  `tuning_outcomes` table and a DDL bump arrive with the DAG runner; records and results are durable.
- **`SimScenario.model` overrides scalars only**; a scenario varying a capacitance matrix needs a nested
  value `AttrValue` does not allow (ADR 0048).
- **No DAG runner, no second node, no API route for nodes, no Flight Deck DAG display** yet.
- **QDAC-II (firmware 14-1.70), for QDevil:** filter setting changes nothing; LOW sense range reads ≈ 2 nA
  for any current; ch02 dead (`*RST` no cure); output impedance 50 Ω. **The 2450 autoranges to 10 nA at
  0 V** and then charges a cable at 10 nA. Bench quirks in BENCH.md.
- Step 5 carry-overs, now Step 6 open decisions: nothing in a sweep plays a waveform; a sweep leaves its
  last level; captures sequential, one channel each; no 3-D capture view; Flight Deck offers every method
  on every record; the trace view has no axes, labels or output curve.
- **The exponential's edge detector is a heuristic** (0046); **the plane fit is OLS** (0045). OPX input
  offset −1.7 mV not applied; OPX `drive` unsupported on the LF-FEM stage.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecations:** the QUA config's `version` key; `job.halt` for `job.cancel`.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human:**
1. Merge the PR.
2. Say what the second node is. Candidates the sim can already oracle: the sensor's Coulomb diamonds
   (`detect_diamonds`, ADR 0030: period, charging energy, lever arm → a sensor operating point), or a
   stability diagram *in virtual gates* that consumes `charge-lattice`'s `M` and checks the honeycomb
   straightened (the first node's outputs used downstream). The second shows the DAG edge; the first
   shows a different physics.
3. Order the rest of Step 6's Open decisions (step file); the QDevil report.

**Then (sessions):** the DAG runner over `depends_on` (one `TuneUp` lifecycle object, outcomes
persisted: `tuning_outcomes` table, DDL bump, ADR); the second node and its fixture; `POST /tuneups`
and Flight Deck's DAG state display (FINISH_LINE); a `PlayedWaveform` activity when a node needs it.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:** a chop's difference is recorded (0037); additive changes without a version bump are
  accepted (0037); the operating point comes before Step 5 (0038); wall-clock CI gates are advisory
  (0039); no surrogate DUT (0040); drivers first, simple; fits later (0041); bench reports write
  themselves (0042); USB serial counts for the QDAC-II (0043); drivers are recreated here rather than
  adapted from QCoDeS (discussion, no ADR); the OPX input constants are measured, not assumed (0044);
  the combiner board stands in for the bias tee and is characterised by a probe before it is used
  (Probe 03); the plane fit is written ahead of the sink decision.
- **2026-10-14, tabled:** Flight Deck should visualise time-series data (scope records first). A renderer,
  not a schema change. Partly done 2026-10-15 (record traces draw as traces with markers).
- **2026-10-15:** the scope is L2-1's sink; waveform capture is a server feature (ADR 0047); how fast the
  QDAC can be stepped matters for untriggered sweeps (Probe 04); finish the OPX conformance rows and L2-2
  before closing Step 5; Step 5 closes and Step 6 opens; **"continue"**: the schema slice and the first
  node first, bench-facing decisions deferred until a node needs them (session 2, ADR 0048).

## Decisions pending
- The second node (sensor diamonds, or a virtual-gate stability diagram consuming `M`).
- Step 6's Open decisions (step file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- Persisting node outcomes (with the DAG runner); a `TuneUp` lifecycle object.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; a default operating point per device; the dot model's
  zero-clipping; the diamond estimator on warm edges.
