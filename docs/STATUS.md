# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6 — Closed-loop tuning → `docs/steps/06-closed-loop-tuning.md` (IN PROGRESS, opened 2026-10-15).
**Branch:** `step-6/virtual-gates` (PR against `main`; the human merges). PRs #25–#43 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 3 (not at the bench). **The DAG edge** (ADR 0049; the human chose
the virtual-gate node over the diamonds). `SweepAxis.couplings` makes a stepped axis a virtual gate: its
companions (other `LevelSource` channels) move from their held level or 0 by volts per volt of the axis;
compile resolves them, the executor sets them with the axis; the inner pulse axis is virtual through
`Affine.scale`, which the pulse slice already had. `InputBinding` on `CalibrationNode.inputs` and
`qdt_tuning.bind` carry an upstream node's outputs into a definition by dotted path. `virtual_gates` also
outputs the compensation coefficients `c_21`, `c_12`; the new rule `straightened` accepts axis-aligned
transitions. The second node, **`virtual-lattice`**, runs after `charge-lattice` through
`qdt_server.tuning.run_tuneup` (nodes in order, inputs bound from accepted outcomes, stop at the first that
is not accepted) and is **accepted on both scenarios**: residual cross ratios −0.008/−0.004 (noisy) and
−0.003/+0.007 (quiet), down from 0.21 in real gates; a 96 × 96 two-node tune-up takes 1.1 s on the sim.
Four `SimResult` fixtures reproduced in CI (`charge_lattice_*`, `virtual_lattice_*`).

## Step 6 exit criteria (from the step file)
| Criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | ◐ two nodes chained through bound inputs, in a list; no persisted lifecycle, no topological sort, no API route |
| first L3 contact as confirmation, not discovery | not started |

## Done
- **Steps 0–5 DONE.** ADR 0001–0049. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033; Step 6 objects beside it by 0048, 0049), control (0036; amended additively by 0046).
- **Step 6 so far:** the modeling objects (`SimScenario`, `DecisionRule`, `CalibrationNode` + `InputBinding`,
  `NodeOutcome`, `SimResult`); `qdt-tuning` (pure: `nodes`, `decisions`, `bind`); `run_node`, `run_tuneup`;
  the `charge-lattice` and `virtual-lattice` nodes; virtual gates in the sweep; scenario realization in
  `qdt-sim`; `scripts/make_tuning_fixtures.py`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `apps/flightdeck`.
- 378 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 71 unit tests and 5 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/virtual-gates` awaits the human.

## Known broken / not yet real
- **`run_tuneup` is a list, not a graph:** the caller orders the nodes; no topological sort, no parallel
  branches, no retries; outcomes are not persisted (a `TuneUp` lifecycle object, a `tuning_outcomes`
  table and a DDL bump come together, ADR 0048/0049); no `POST /tuneups`; no Flight Deck DAG display.
- **`InputBinding.target` is a string path checked at bind time**, not at import; the node constructors
  keep template and bindings together and `test_bind.py` pins them.
- **A coupled companion follows the axis value from its held level or 0**, never from where it was; a
  sweep that wants another origin holds it in `levels` (ADR 0049).
- **Flight Deck's sweep form does not expose couplings**; a virtual sweep is crafted as data (a node) for
  now. The bench has one OPX pulse line cabled, so the virtual pulse axis cannot run there yet.
- **`detect_transitions` reports `ok` on a noiseless, nearly constant map** (a degenerate lattice); a
  method fix is a `VERSION` bump (ADR 0029).
- **`SimScenario.model` overrides scalars only** (ADR 0048).
- **QDAC-II (firmware 14-1.70), for QDevil:** filter setting changes nothing; LOW sense range reads ≈ 2 nA
  for any current; ch02 dead (`*RST` no cure); output impedance 50 Ω. **The 2450 autoranges to 10 nA at
  0 V.** Bench quirks in BENCH.md.
- Step 5 carry-overs, Step 6 open decisions: nothing in a sweep plays a waveform; a sweep leaves its last
  level; captures sequential, one channel each; no 3-D capture view; Flight Deck offers every method on
  every record; the trace view has no axes, labels or output curve.
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
2. Say whether the next session is the **persisted tune-up** (a `TuneUp` lifecycle object over nodes and
   outcomes, topological sort over `depends_on`, a `tuning_outcomes` table with a DDL bump, `POST /tuneups`
   and `GET /tuneups/{id}`; then Flight Deck's DAG state display and click-to-set from FINISH_LINE), or a
   **third node** first (the sensor's Coulomb diamonds → a sensor operating point, consumed by the
   stability nodes through `levels`).
3. The QDevil report; the Step 6 Open decisions still waiting (`PlayedWaveform`, sub-ms stepping, sense
   range declaration, rest level).

**Then (sessions):** whichever of the two the human picks; the other after; a bench confirmation of the
two-node tune-up once a second OPX pulse line is cabled (the node is stand-agnostic).

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
  before closing Step 5; Step 5 closes and Step 6 opens; the schema slice and the first node first (ADR
  0048); **the second node is the virtual-gate stability diagram, not the diamonds** (ADR 0049).

## Decisions pending
- Next: the persisted tune-up (lifecycle object, sort, table, API, DAG display) or a third node first.
- Step 6's Open decisions (step file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; a default operating point per device; the dot model's
  zero-clipping; the diamond estimator on warm edges.
