# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6 — Closed-loop tuning → `docs/steps/06-closed-loop-tuning.md` (IN PROGRESS, opened 2026-10-15).
**Branch:** `step-6/persisted-tuneup` (PR against `main`; the human merges). PRs #25–#44 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 4 (not at the bench). **The persisted tune-up** (ADR 0050).
`TuneUp` (control slice, beside `Run`) is the lifecycle: nodes in topological order (`qdt_tuning.order`),
outcomes so far, queued → running → completed | stopped | failed, kept in the server's memory. `NodeOutcome`
is persisted (`tuning_outcomes`, DDL v3, synced after results; `Registry.add_outcome`/`outcomes`/`outcome`).
`TuneUpManager` runs each node's sweep through the `RunManager`, so every node's map is live on the stream
and recorded like any run, then the catalogue method, the rule and `add_outcome`; it stops at the first
outcome that is not accepted, or between nodes on request. API: `GET /nodes` (the templates for the
stand's sequencer, `qdt_tuning.nodes.TEMPLATES`), `POST /tuneups` (node ids in any order, options, an
optional `SimScenario` that becomes the run options and tags the outcomes), `GET /tuneups[/{id}]`,
`POST /tuneups/{id}/stop`, `GET /outcomes[?tuneup_id&node_id&status]`, `GET /outcomes/{id}`. Flight Deck's
control panel gained a **Tune-up section**: the nodes with their dependencies, "run tune-up", "stop", and
the DAG state rendered from the `TuneUp` (`tuneupLines`, pure and unit-tested). **The two-node tune-up
completes unattended through the API and from the UI on the simulator** (an e2e test watches it).

## Step 6 exit criteria (from the step file)
| Criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | ✔ on the simulator: `charge-lattice → virtual-lattice` from `POST /tuneups` and from Flight Deck, outcomes in the registry (2026-10-15). Two nodes so far; more nodes extend it |
| first L3 contact as confirmation, not discovery | not started (needs a fridge; the bench can confirm the same tune-up once a second OPX pulse line is cabled) |

## Done
- **Steps 0–5 DONE.** ADR 0001–0051 (0051 is a Step 7 decision taken ahead of its step). Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033; Step 6 objects beside it by 0048–0050), control (0036; amended additively by
  0046; `TuneUp` beside it by 0050). Registry DDL v3 (0026, 0029, 0050).
- **Step 6 so far:** the modeling objects; `qdt-tuning` (pure: `nodes` + `TEMPLATES`, `decisions`, `bind`,
  `dag.order`); `run_node`, `run_tuneup`, `TuneUpManager`; the `charge-lattice` and `virtual-lattice` nodes;
  virtual gates in the sweep; scenario realization in `qdt-sim`; the tune-up API; Flight Deck's Tune-up
  section; `scripts/make_tuning_fixtures.py`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `apps/flightdeck`.
- 387 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 72 unit tests and 6 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/persisted-tuneup` awaits the human.

## Known broken / not yet real
- **`TuneUp` is not persisted:** a server restart forgets which outcomes belonged together except through
  their shared `tuneup_id` on the stored outcomes; a `tuneups` table is a later additive change.
- **One tune-up at a time; a stop takes effect between nodes; no parallel branches, retries or resume.**
- **Flight Deck's sweep form does not expose couplings; no click-to-set yet** (FINISH_LINE's one "up"
  edge). The Tune-up section runs templates only; custom nodes are posted as data.
- **The bench has one OPX pulse line cabled**, so the virtual pulse axis (and the two-node tune-up) cannot
  run there yet; the nodes are stand-agnostic.
- **`detect_transitions` reports `ok` on a noiseless, nearly constant map** (a degenerate lattice); a
  method fix is a `VERSION` bump (ADR 0029).
- **`SimScenario.model` overrides scalars only** (ADR 0048). **`InputBinding.target` is a string path**
  checked at bind time (ADR 0049).
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
2. Choose the next session: the **third node** (the sensor's Coulomb diamonds → a sensor operating point,
   consumed by the stability nodes through `levels`, which needs `InputBinding` into `levels` and a
   scenario whose sensor is cold enough for `detect_diamonds`, ADR 0030), **click-to-set** (Flight Deck
   emits a set-level request; a `POST /levels` or a one-point sweep; the one "up" edge), or a **bench
   confirmation** of the two-node tune-up (cable a second OPX pulse line to the combiner's pulse input or
   to a second board; `qdt-server --stand` and `POST /tuneups`).
3. The QDevil report; the Step 6 Open decisions still waiting (`PlayedWaveform`, sub-ms stepping, sense
   range declaration, rest level).

**Then (sessions):** the chosen item; a `tuneups` table when something reads tune-up history; resume and
parallel branches when a DAG needs them.

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
  0048); the second node is the virtual-gate stability diagram (ADR 0049); **"start the next step"**: the
  persisted tune-up before a third node (ADR 0050); **`qdt-telemetry` ingests cryo context from the lab's
  existing fridge monitoring and does not collect** (ADR 0051, decided in a separate chat and applied from
  its patch; Analyses 0003 and 0004 arrived the same way).

## Decisions pending
- Next: the third node, click-to-set, or a bench confirmation of the tune-up.
- Step 6's Open decisions (step file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table (when something reads tune-up history); resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; a default operating point per device; the dot model's
  zero-clipping; the diamond estimator on warm edges.
