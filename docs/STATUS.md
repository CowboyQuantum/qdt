# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6b — Flight Deck workspace → `docs/steps/06b-flightdeck-workspace.md` (IN PROGRESS, opened
2026-10-15). Step 6 is DONE (closed 2026-10-15; its L3 confirmation is the first fridge task, below). Step 7
waits for manager sign-off.
**Branch:** `step-6b/sweep-pulse` (PR against `main`; the human merges). PRs #25–#53 merged 2026-10-14/16.
**Last session:** 2026-10-16, Step 6b session 3 (not at the bench). **Sweep + Pulse widgets, one Run**,
deliverable 3 of six (ADR 0056). The Sweep widget is the sweep form over the unchanged pure builders (kind,
axes, sensor, shots, capture, operating-point levels, options) with a compile button; it holds the compiled
plan and answers the strip's one Run: if the editors changed since the compile it compiles again, then runs,
and follows the run. The strip shows `plan 1234abcd`, marks it `· stale` on any edit, shows the run's state
with an abort button, and disables Run while a run is live. The Pulse widget is the sequence editor over the
unchanged pure model; it follows the Sweep widget's template (`sweep:axes`) until edited and publishes its
sequence (`pulse:sequence`); a stage sweep needs it mounted. `panel.ts` lost the sweep form, the pulse editor
and the Runs list (850 → 330 lines); the tune-up runner has its own options field. The default layout is
sweep + control | plot | pulse + history under a versioned key (`flightdeck.layout.v2`). The e2e control
test compiles, sees the identity and the stale marker, and runs from the strip. The step's exit criterion
"exactly one Run control, bound to a compiled plan with a visible identity and stale marker" is met.

## Step 6b deliverables (step file; one session each)
| # | Deliverable | State |
|---|---|---|
| 1 | Shell: themes as data, strip, layout model, widget registry, bus; panel mounted unchanged | ✔ session 1 (ADR 0054) |
| 2 | Plot panes: N instances over the shared stores, ⚙ menu, follow-live or pinned; History widget | ✔ session 2 (ADR 0055) |
| 3 | Sweep + Pulse widgets; Run moves to the strip, bound to the compiled plan with a stale marker | ✔ session 3 (ADR 0056) |
| 4 | Levels (operating point) widget with readbacks (`GET /levels` + `LevelSense`, own ADR); Virtual gates widget | next |
| 5 | Methods + Tune-up widgets; `panel.ts` deleted; `e2e/control.test.ts` migrated | — |
| 6 | Script widget placeholder | — |

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 DONE.** ADR 0001–0056. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021), stand/activity/pulse
  (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033;
  Step 6 objects beside it by 0048–0050), control (0036; amended additively by 0046; `TuneUp` beside it by
  0050). Registry DDL v3 (0026, 0029, 0050).
- **Step 6:** `qdt-tuning`; three nodes; virtual gates; the tune-up API; the held operating point and `/levels`;
  Flight Deck's Tune-up section and click-to-set.
- **Step 6b so far:** the shell (1); plot panes and History (2); Sweep and Pulse widgets, one Run (3). Widgets:
  `plot`, `sweep`, `pulse`, `history`, `control` (what is left of the Step 4b panel: held operating point,
  records, analysis, tune-up), `empty`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 394 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 109 unit tests and 9 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/sweep-pulse` awaits the human.

## Known broken / not yet real
- **A stage sweep needs the Pulse widget mounted**: its sequence lives in that pane; with the pane closed, Run
  on a stage sweep is refused with a message. The DC and capture kinds do not need it.
- **One run at a time from the UI**: the strip follows the run the Sweep widget started; a second Run while one
  is live is refused (the server could queue it; the UI does not yet).
- **Run compiles again when stale** rather than refusing: the identity in the strip is always of a plan compiled
  from the editors' state, never one they moved past (ADR 0056). The `ExecutionPlan` is read for its id and a
  summary only; a plan viewer is a later widget.
- **No colormap in the ⚙ menu**; **per-pane view state does not survive a reload** (ADR 0055).
- **The panel's Records list and "show" duplicate History** until deliverable 5. The strip's stand/device come
  from the API; without a server they read "?".
- **History refreshes on a run's final chunk and on `records:changed`** (the Sweep widget emits it when a run
  ends); no server push exists.
- **No Google Fonts link**: the Plex stacks fall back to system fonts (the bench is offline).
- **`provenance_check.sh` matches its terms as bare substrings**; a word-boundary pattern is a one-line fix.
- Step 6 carry-overs: the held operating point is server memory (a `stand_state` table later); click-to-set only
  for axes named after stand DC channels; `flank_offset_v` is a judgment (0052); the diamonds method needs a cold
  sensor (0030); `TuneUp` not persisted, one at a time, no resume/parallel (0050); the sweep form hides
  couplings; the bench has one OPX pulse line and no `SG`/`bias`/`sensor`; `detect_transitions` reports `ok` on
  a constant map; `SimScenario.model` overrides scalars only; QDAC-II quirks (BENCH.md); nothing in a sweep plays
  a waveform; captures sequential; the trace view has no axes/labels/output curve; the exponential's edge
  detector is a heuristic (0046); the plane fit is OLS (0045); OPX input offset not applied; `bench_report.py`
  does not redact serials; qm-qua deprecations; zero-clipping in the dot model (0020); Postgres suite only in
  CI; `FINISH_LINE.md` TODO (human); Windows pnpm via `corepack pnpm`.

## Next action
**Sessions:** Step 6b deliverable 4, **the Levels (operating point) widget and the Virtual gates widget**.
First the server: `GET /levels` gains a readback per channel where the stand declares a `LevelSense`
(setpoint + readback; an ADR decides null vs. omitted when a channel has no sense, Open decisions). Then
`src/widgets/levels.ts` over ADR 0038's fixed levels: every DC channel of the stand, filterable (type,
instrument, text, pinned, near-limit; AND across groups, OR within), sortable, pinnable, inline set with limit
refusal and a settling state; it absorbs the panel's click-to-set section (`map:click` → offer → set). Then
`src/widgets/gates.ts` over ADR 0049 couplings (the matrix the sweep form does not expose yet). e2e: click
the map → the Levels widget offers the point → set → held → readback → release.

**Human:**
1. Merge the PR; try compile → edit → stale → Run in `pnpm dev` against `python -m qdt_server`.
2. Decide for deliverable 4: `GET /levels` readback when a channel has no `LevelSense` — null or omitted
   (STATUS's default: `readback: null`), and whether limits come from the `ChannelMap` (a new optional field,
   additive) or stay a UI default.
3. Step 6's Open decisions (its file) and the QDevil report still wait.

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
- **2026-10-15:** the scope is L2-1's sink; waveform capture is a server feature (ADR 0047); Probe 04; finish the
  OPX conformance rows and L2-2 before closing Step 5; Step 5 closes and Step 6 opens; the schema slice and the
  first node first (ADR 0048); the second node is the virtual-gate stability diagram (ADR 0049); the persisted
  tune-up before a third node (ADR 0050); `qdt-telemetry` ingests, does not collect (ADR 0051); the third node is
  the sensor operating point (ADR 0052); click-to-set (ADR 0053); "let's strike the DAPS development for now";
  the Step 6b spec arrives as a chat patch (ADR 0054); "let's put off L3 and close step 6": Step 6 closes on the
  simulator, the L3 confirmation is the first fridge task; "go with 6b": Step 6b opens, ADR 0054 is accepted,
  the shell is session 1; PRs #52 and #53 merged without a word, so sessions 2 (ADR 0055) and 3 (ADR 0056)
  followed the step file's order.

## Decisions pending
- Deliverable 4: `GET /levels` readback semantics (null vs. omitted); channel limits in the `ChannelMap` or a UI
  default.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- A Google Fonts link for online use; a colormap choice (renderer slice); queueing a second run from the UI.
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
