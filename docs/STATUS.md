# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6b — Flight Deck workspace → `docs/steps/06b-flightdeck-workspace.md` (IN PROGRESS, opened
2026-10-15). Step 6 is DONE (closed 2026-10-15; its L3 confirmation is the first fridge task, below). Step 7
waits for manager sign-off.
**Branch:** `step-6b/plot-panes` (PR against `main`; the human merges). PRs #25–#52 merged 2026-10-14/16.
**Last session:** 2026-10-15/16, Step 6b session 2 (not at the bench). **Plot panes and History**, deliverable
2 of six (ADR 0055). The `plot` widget is any number of centre panes over the shared `Datasets`, each with its
own `MapRenderer` (disposed when the pane closes), view options and line cut. A pane follows the stream (the
newest Dataset as it arrives) or is pinned to one Dataset from its ⚙ menu (dataset, variable, minus, transform,
swap axes, cut; focus-trapped, Escape closes and returns focus). Only following panes drive the strip's pill,
telemetry and progress. `history` lists `/records`, searches, shows which panes show a record, and opens one
in an existing or a new pane: the server replays it on the stream and the pane pins itself to the Dataset
that is the record (by registry ref, or by the record's plan id when its run is still on the stream, since
the server then publishes only the overlays). Six panes at most (`MAX_PLOT_PANES`, one WebGL2 context each;
closes that open decision). The full display map (stack mean → transform → swap) is one pure function and
two panes over one store are byte-identical. The e2e tests now address panes by position and menu, never by
id; the control e2e opens the run's record from History into Plot 2 while Plot 1 follows live and moves Plot
2's cut on its own.

## Step 6b deliverables (step file; one session each)
| # | Deliverable | State |
|---|---|---|
| 1 | Shell: themes as data, strip, layout model, widget registry, bus; panel mounted unchanged | ✔ session 1 (ADR 0054) |
| 2 | Plot panes: N instances over the shared stores, ⚙ menu, follow-live or pinned; History widget | ✔ session 2 (ADR 0055) |
| 3 | Sweep + Pulse widgets; Run moves to the strip, bound to the compiled plan with a stale marker | next |
| 4 | Levels (operating point) widget with readbacks (`GET /levels` + `LevelSense`, own ADR); Virtual gates widget | — |
| 5 | Methods + Tune-up widgets; `panel.ts` deleted; `e2e/control.test.ts` migrated | — |
| 6 | Script widget placeholder | — |

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 DONE.** ADR 0001–0055. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021), stand/activity/pulse
  (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033;
  Step 6 objects beside it by 0048–0050), control (0036; amended additively by 0046; `TuneUp` beside it by
  0050). Registry DDL v3 (0026, 0029, 0050).
- **Step 6:** `qdt-tuning`; three nodes; virtual gates; the tune-up API; the held operating point and `/levels`;
  Flight Deck's Tune-up section and click-to-set.
- **Step 6b so far:** the shell (session 1); plot panes and History (session 2). Widgets: `plot`, `control`
  (the Step 4b panel, unchanged, temporary), `history`, `empty`. Default layout: control | plot | history.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 394 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 107 unit tests and 9 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/plot-panes` awaits the human.

## Known broken / not yet real
- **No colormap in the ⚙ menu**: the renderers share one viridis formula (shader and CPU oracle); a second
  colormap is a renderer change with pixel tests, its own slice.
- **Per-pane view state (follow/pinned, variable, transform, swap, cut) does not survive a reload**; the layout
  persists which panes exist. A `view` field on the persisted pane is an additive change when wanted.
- **The strip's Run and next-run line read the control panel's form** (the panel is unchanged): two Run
  controls until deliverable 3. The panel's Records list and "show" duplicate History until deliverable 5.
  The strip's stand/device come from the API; without a server they read "?".
- **History refreshes on a stream Dataset's final chunk (twice, 0.5 s and 3 s later)** because the record lands
  after the run finishes; there is no `records:changed` event from the server. A manual refresh button exists.
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
**Sessions:** Step 6b deliverable 3, **Sweep + Pulse widgets**: extract the sweep form (kind, axes, sensor,
shots, capture, operating-point levels, options) and the pulse-sequence editor from `panel.ts` into
`src/widgets/sweep.ts` and `src/widgets/pulse.ts` over the unchanged pure models (`control/sweeps.ts`,
`control/sequence.ts`); the sweep widget compiles (`POST /compile`) and publishes the plan's identity on the
bus; the strip's Run binds to that compiled plan, shows its id, marks it stale when an editor changes after
the compile, and starts the run; editors never run. The panel keeps runs/records/analysis/tune-up/levels
until deliverables 4–5. e2e: compile → Run from the strip → record in History → open in Plot 2 → overlay.

**Human:**
1. Merge the PR; try the ⚙ menu and History's "open in a new pane" in `pnpm dev` against `python -m qdt_server`.
2. Say whether the panel's own run button should be hidden now that the strip's Run exists, and whether a
   Google Fonts link is wanted.
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
  the shell is session 1; PR #52 merged, so session 2 (plot panes, ADR 0055) followed without a new word.

## Decisions pending
- Step 6b's Open decisions (its file): layout as a schema object; `/levels` readback semantics; the script
  sandbox; the release mirror's first widgets; themes per browser or in the registry.
- Two Run controls until deliverable 3; a Google Fonts link for online use; a colormap choice (renderer slice).
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
