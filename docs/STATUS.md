# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6 — Closed-loop tuning → `docs/steps/06-closed-loop-tuning.md` (IN PROGRESS, opened 2026-10-15).
**Branch:** `step-6/click-to-set` (PR against `main`; the human merges). PRs #25–#47 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 6 (not at the bench). **Click-to-set** (ADR 0053), the listed
deliverable and FINISH_LINE's one "up" edge. The server holds the stand's operating point: `POST /levels`
validates the channels (on the stand, on a `LevelSource`), sets them on the backends now and holds them;
`GET /levels` reads them; `DELETE /levels` releases them. Every sweep the `RunManager` compiles or runs is
first merged with the held levels for the channels it does not touch (axes, couplings, sensed, captured,
its own `levels`), so the plan and the record carry the operating point they ran at; tune-up nodes inherit
it the same way, and a node that holds a channel itself (`charge-lattice` on `SG`) overrides it for that
channel. Flight Deck: a click on the heatmap yields the point under it as coordinate names and values
(`pointAt`, rule 8: no channels, no instruments); the panel maps names to the stand's DC channels
(`setpointFor`), offers "set … on the stand", shows what is held and releases it. e2e: click the map, set,
held, release. This closes the pending default-operating-point decision: the server is where it lives.

## Step 6 exit criteria (from the step file)
| Criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | ✔ three nodes (sensor → lattice → virtual gates) from `POST /tuneups` and from Flight Deck; outcomes in the registry |
| first L3 contact as confirmation, not discovery | not started (needs a fridge) |

**Deliverables (step file):** DAG runner ✔ (ADR 0050); nodes verified against sim ✔ (three, ADR 0048, 0049,
0052); Flight Deck click-to-set ✔ (ADR 0053); DAPS forward model + bias study as sim scenarios + analysis
routines — not started (the one deliverable left; it needs the physics decisions in the step's Open list).

## Done
- **Steps 0–5 DONE.** ADR 0001–0053 (0051 is a Step 7 decision taken ahead of its step). Frozen: `Dataset`
  (0015; v2 by 0031), protocols (0021), stand/activity/pulse (0022; amended additively by 0037, 0038, 0047,
  0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; Step 6 objects beside it by 0048–0050),
  control (0036; amended additively by 0046; `TuneUp` beside it by 0050). Registry DDL v3 (0026, 0029, 0050).
- **Step 6 so far:** the modeling objects; `qdt-tuning` (pure: `nodes` + `TEMPLATES`, three `decisions`,
  `bind`, `dag.order`); `run_node`, `run_tuneup`, `TuneUpManager`; three nodes; virtual gates in the sweep;
  scenario realization and truth in `qdt-sim`; the tune-up API; the held operating point and `/levels`;
  Flight Deck's Tune-up section and click-to-set; `scripts/make_tuning_fixtures.py`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `apps/flightdeck`.
- 394 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 74 unit tests and 6 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/click-to-set` awaits the human.

## Known broken / not yet real
- **The held operating point is server memory** (like runs and tune-ups): a restart forgets it and the
  stand stays where it is; records carry it per sweep. A `stand_state` table is a later additive change.
- **Click-to-set resolves to the cell under the pointer, and only axes named after stand DC channels are
  settable** (`P1`, `P2`; not `V_sd` on `bias`); the panel does not yet read a record's definition for
  the axis → channel map.
- **`flank_offset_v` is a judgment, not an estimate** (ADR 0052); **the diamonds method needs a cold
  sensor** (ADR 0030).
- **`TuneUp` is not persisted; one tune-up at a time; stop between nodes; no parallel branches, retries
  or resume** (ADR 0050). **The sweep form does not expose couplings; the Tune-up section runs templates
  only.**
- **The bench has one OPX pulse line cabled and no `SG`/`bias`/`sensor` channels.**
- **`detect_transitions` reports `ok` on a noiseless, nearly constant map**; a method `VERSION` bump.
- **`SimScenario.model` overrides scalars only**; **`InputBinding.target` is a string path**.
- **QDAC-II (firmware 14-1.70), for QDevil:** filter setting changes nothing; LOW sense range reads ≈ 2 nA
  for any current; ch02 dead (`*RST` no cure); output impedance 50 Ω. **The 2450 autoranges to 10 nA at
  0 V.** Bench quirks in BENCH.md.
- Step 5 carry-overs, Step 6 open decisions: nothing in a sweep plays a waveform; a sweep leaves its last
  level (now the held operating point says where the stand *should* be); captures sequential, one
  channel each; no 3-D capture view; Flight Deck offers every method on every record; the trace view has
  no axes, labels or output curve.
- **The exponential's edge detector is a heuristic** (0046); **the plane fit is OLS** (0045). OPX input
  offset −1.7 mV not applied; OPX `drive` unsupported on the LF-FEM stage.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecations:** the QUA config's `version` key; `job.halt` for `job.cancel`.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.
- `chat-2026-10-15-series.patch` sits untracked at the repo root (the human's upload; fully applied).

## Next action
**Human:**
1. Merge the PR.
2. Step 6 has one deliverable left, the **DAPS forward model + bias study as sim scenarios and analysis
   routines**, and its L3 confirmation. Say what the DAPS study is to measure and which physics it needs
   (the step's Open decisions list tunnel coupling and bias triangles, ADR 0020, 0030); a session then
   writes the scenario, the method and the node. Or name the next slice instead: a `sensor_peak` method
   (retires `flank_offset_v`), a bench confirmation of the stability nodes (a second OPX pulse line), or
   the `PlayedWaveform` activity.
3. The QDevil report; the Step 6 Open decisions still waiting.

**Then (sessions):** the chosen item; a `tuneups` table and a `stand_state` table when something reads
them; resume and parallel branches when a DAG needs them.

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
  0048); the second node is the virtual-gate stability diagram (ADR 0049); the persisted tune-up before a
  third node (ADR 0050); `qdt-telemetry` ingests, does not collect (ADR 0051, from a separate chat's
  patch); the third node is the sensor operating point (ADR 0052); **"continue to next session"**:
  click-to-set, the listed deliverable (ADR 0053).

## Decisions pending
- The DAPS forward model + bias study: what it measures, which physics it needs.
- Step 6's Open decisions (step file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end (the held operating point now says where the stand should be); the
  time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
