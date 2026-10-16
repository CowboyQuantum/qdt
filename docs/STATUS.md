# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. **Step 6 — Closed-loop tuning is DONE** (closed 2026-10-15; L3 deferred).
The next step is the human's choice: **6b — Flight Deck workspace** (`docs/steps/06b-flightdeck-workspace.md`,
spec merged in PR #50, ADR 0054 proposed) or **7 — Other sources** (`docs/steps/07-other-sources.md`, gated by
manager sign-off, plan Open Decision #5).
**Branch:** `step-6/close` (PR against `main`; the human merges). PRs #25–#50 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 8 (not at the bench). Housekeeping and the close. Applied the chat
patch for Step 6b as PR #50 (ADR renumbered 0051 → 0054 because 0051 is the telemetry ADR; the ADR title reworded
because the provenance grep matched a substring of an ordinary word). Then, on the human's word ("let's put off L3 and close step 6"),
marked Step 6 DONE in its file and `docs/steps/README.md`. No ADR: the rule that L3 never gates a step is plan
§7.1; the direction line below records the call.

## Step 6 close-out
| Exit criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | ✔ three nodes (sensor → lattice → virtual gates) from `POST /tuneups` and from Flight Deck; outcomes in the registry |
| first L3 contact as confirmation, not discovery | **deferred** — the first fridge task (below); plan §7.1: L3 is never a step exit criterion |

Deliverables: DAG runner ✔ (ADR 0050); nodes verified against sim ✔ (three, ADR 0048, 0049, 0052); click-to-set ✔
(ADR 0053); DAPS forward model + bias study — struck 2026-10-15 by the human.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 DONE.** ADR 0001–0054 (0051 is a Step 7 decision taken ahead of its step; 0054 is Proposed, for
  Step 6b). Frozen: `Dataset` (0015; v2 by 0031), protocols (0021), stand/activity/pulse (0022; amended additively
  by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; Step 6 objects beside it by
  0048–0050), control (0036; amended additively by 0046; `TuneUp` beside it by 0050). Registry DDL v3 (0026, 0029,
  0050).
- **Step 6:** the modeling objects; `qdt-tuning` (pure: `nodes` + `TEMPLATES`, three `decisions`, `bind`,
  `dag.order`); `run_node`, `run_tuneup`, `TuneUpManager`; three nodes; virtual gates in the sweep; scenario
  realization and truth in `qdt-sim`; the tune-up API; the held operating point and `/levels`; Flight Deck's
  Tune-up section and click-to-set; `scripts/make_tuning_fixtures.py`.
- **Step 6b spec:** step file, ADR 0054 (Proposed), `docs/examples/flightdeck-workspace-proto.html` and
  `flightdeck-theme-ember.json` as design reference only.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 394 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 74 unit tests and 6 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/close` (docs only) awaits the human.

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
- Step 5/6 carry-overs: nothing in a sweep plays a waveform; a sweep leaves its last level (the held operating
  point says where the stand *should* be); captures sequential, one channel each; no 3-D capture view; Flight
  Deck offers every method on every record; the trace view has no axes, labels or output curve.
- **The exponential's edge detector is a heuristic** (0046); **the plane fit is OLS** (0045). OPX input
  offset −1.7 mV not applied; OPX `drive` unsupported on the LF-FEM stage.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecations:** the QUA config's `version` key; `job.halt` for `job.cancel`.
- Carried over: zero-clipping in the dot model (ADR 0020); overlays in one colour; Postgres suite only in CI;
  `FINISH_LINE.md` TODO (human); Windows pnpm via `corepack pnpm`.
- `provenance_check.sh` matches its terms as bare substrings, so an ordinary word can trip it (it did, in the
  Step 6b ADR title); a word-boundary pattern is a one-line fix when it next bites.

## Next action
**Human:**
1. Merge the PR.
2. **Name the next step.** The default is **Step 6b, deliverable 1 (the shell)**: themes as data, the top strip,
   the workspace layout model, widget registry and bus, the existing control panel mounted unchanged. It starts
   after click-to-set, which has landed, and it needs no sign-off. Starting it accepts ADR 0054; say so, or say
   what in the ADR changes first. **Step 7** waits for manager sign-off (Open Decision #5).
3. Or a slice outside a step first: a `sensor_peak` method (retires `flank_offset_v`), a bench confirmation of
   the stability nodes (a second OPX pulse line), or the `PlayedWaveform` activity.
4. The QDevil report; Step 6's Open decisions (its file) still waiting.

**Then (sessions):** the chosen item. The first 6b session opens its file (Status → IN PROGRESS), flips ADR 0054
to Accepted, and builds the shell. A `tuneups` table and a `stand_state` table when something reads them;
resume and parallel branches when a DAG needs them.

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
  patch); the third node is the sensor operating point (ADR 0052); "continue to next session":
  click-to-set, the listed deliverable (ADR 0053); "let's strike the DAPS development for now": the
  DAPS forward model and bias study leave Step 6's deliverables (session 7); the Step 6b spec arrives as a
  chat patch (ADR 0054, Proposed); **"let's put off L3 and close step 6"**: Step 6 closes on the simulator,
  the L3 confirmation is the first fridge task (session 8).

## Decisions pending
- The next step: 6b (default) or 7; accepting ADR 0054.
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- Step 6b's Open decisions (its file): layout as a schema object; the WebGL2 context cap; `/levels` readback
  semantics; the script sandbox; the release mirror's first widgets; themes per browser or in the registry.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
