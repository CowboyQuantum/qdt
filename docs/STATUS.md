# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6b — Flight Deck workspace → `docs/steps/06b-flightdeck-workspace.md` (IN PROGRESS, opened
2026-10-15). Step 6 is DONE (closed 2026-10-15; its L3 confirmation is the first fridge task, below). Step 7
waits for manager sign-off.
**Branch:** `step-6b/analysis-tuneup` (PR against `main`; the human merges). PRs #25–#55 merged 2026-10-14/16.
**Last session:** 2026-10-16, Step 6b session 5 (not at the bench). **Analysis and Tune-up widgets; the panel
deleted**, deliverable 5 of six (ADR 0058). The Analysis widget: a record from History's per-row "analyse"
(`analysis:record`) or its own picker over `/records`, a method from `/methods`, parameters over the pure
`control/methods.ts`, run, estimates, show overlays and show output through the replay path. The Tune-up
widget: nodes from `/nodes`, options, start/stop, the DAG state rendered from `TuneUp` (`tuneupLines` moved,
still pure); a finished tune-up emits `records:changed` like a finished run. `control/panel.ts` and the
`control` widget are deleted; no `#`-ids remain in form widgets; `e2e/control.test.ts` drives every widget by
pane. Default layout sweep + analysis + tune-up | plot | pulse + levels + history (`flightdeck.layout.v4`).
Four of the step's five exit criteria are met (below); the fifth is deliverable 6's placeholder.

## Step 6b deliverables (step file; one session each)
| # | Deliverable | State |
|---|---|---|
| 1 | Shell: themes as data, strip, layout model, widget registry, bus; panel mounted unchanged | ✔ session 1 (ADR 0054) |
| 2 | Plot panes: N instances over the shared stores, ⚙ menu, follow-live or pinned; History widget | ✔ session 2 (ADR 0055) |
| 3 | Sweep + Pulse widgets; Run moves to the strip, bound to the compiled plan with a stale marker | ✔ session 3 (ADR 0056) |
| 4 | Levels (operating point) widget with readbacks (`GET /levels/state`); Virtual gates widget | ✔ session 4 (ADR 0057) |
| 5 | Analysis + Tune-up widgets; `panel.ts` deleted; `e2e/control.test.ts` migrated | ✔ session 5 (ADR 0058) |
| 6 | Script widget placeholder (allowed-API panel, a stage button that only validates) | next |

## Step 6b exit criteria (step file)
| Criterion | State |
|---|---|
| `panel.ts` is gone; every former panel capability exists as a widget; all e2e green | ✔ |
| Two plot panes show live and a stored record simultaneously with independent cuts | ✔ (e2e: History opens the run's record in Plot 2 while Plot 1 follows; Plot 2's cut moves alone) |
| Exactly one Run control, bound to a compiled plan with a visible identity and stale marker | ✔ |
| Layout persists and restores; `+` refuses below the min pane height | ✔ |

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 DONE.** ADR 0001–0058. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021), stand/activity/pulse
  (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033;
  Step 6 objects beside it by 0048–0050), control (0036; amended additively by 0046, 0050; `ChannelLevel` beside
  it by 0057). Registry DDL v3 (0026, 0029, 0050).
- **Step 6:** `qdt-tuning`; three nodes; virtual gates; the tune-up API; the held operating point and `/levels`;
  click-to-set.
- **Step 6b so far:** deliverables 1–5. Widgets: `plot`, `sweep`, `pulse`, `levels`, `gates`, `history`,
  `analysis`, `tuneup`, `empty`. `src/control/` holds only the pure form models.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 395 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 116 unit tests and 9 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/analysis-tuneup` awaits the human.

## Known broken / not yet real
- **An analysis names its record from History or the picker**, not from a plot pane's pinned record yet (the id
  is on the bus; a "from Plot N" choice is a small addition).
- **Two widgets refresh records after a run** (History, Analysis): two requests, no server push.
- **The simulator's live device and a run's device diverge** (ADR 0057); a simulated gate reads back null; the
  Levels widget polls every 2 s; limits are a browser setting; the coupling matrix is per browser.
- **A stage sweep needs the Pulse widget mounted**; **one run at a time from the UI**; **Run compiles again when
  stale** (ADR 0056).
- **No colormap in the ⚙ menu**; **per-pane view state does not survive a reload** (ADR 0055).
- The strip's stand/device come from the API; without a server they read "?". **No Google Fonts link**;
  **`provenance_check.sh` matches bare substrings**.
- Step 6 carry-overs: the held operating point is server memory (a `stand_state` table later); click-to-set only
  for axes named after stand DC channels; `flank_offset_v` is a judgment (0052); the diamonds method needs a cold
  sensor (0030); `TuneUp` not persisted, one at a time, no resume/parallel (0050); the bench has one OPX pulse
  line and no `SG`/`bias`/`sensor`; `detect_transitions` reports `ok` on a constant map; `SimScenario.model`
  overrides scalars only; QDAC-II quirks (BENCH.md); nothing in a sweep plays a waveform; captures sequential;
  the trace view has no axes/labels/output curve; the exponential's edge detector is a heuristic (0046); the
  plane fit is OLS (0045); OPX input offset not applied; `bench_report.py` does not redact serials; qm-qua
  deprecations; zero-clipping in the dot model (0020); Postgres suite only in CI; `FINISH_LINE.md` TODO (human);
  Windows pnpm via `corepack pnpm`.

## Next action
**Sessions:** Step 6b deliverable 6, **the Script widget placeholder**: `src/widgets/script.ts` with a text area, a
panel listing the allowed API (the calls a measurement script may make: sweep, run, wait, analyze, as the
prototype sketched) and a "stage" button that only validates (names outside the allowed list, syntax) and
reports; no execution. A real server-side sandbox is its own ADR (Open decisions), not this step. Then close
Step 6b: step file DONE, `docs/steps/README.md`, the exit-criteria table above checked once more, and STATUS
pointing at what comes next (Step 7 gated by sign-off; otherwise the Step 6 Open decisions or the fridge tasks).

**Human:**
1. Merge the PR; the panel is gone: try an analysis from History's "analyse" and a tune-up from its widget in
   `pnpm dev` against `python -m qdt_server`.
2. After deliverable 6, say what follows Step 6b: Step 7 (needs sign-off), a Step 6 Open decision
   (`PlayedWaveform`, sub-ms stepping, sense range), a `sensor_peak` method, or a bench session.
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
  the shell is session 1; PRs #52–#55 merged without a word, so sessions 2–5 (ADR 0055–0058) followed the step
  file's order, taking STATUS's stated defaults where a decision was pending.

## Decisions pending
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- What follows Step 6b (after deliverable 6).
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- A Google Fonts link for online use; a colormap choice (renderer slice); queueing a second run from the UI;
  pulling the tune-up's `virtual_gates` outputs into the coupling matrix; "analyse the record in Plot N".
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
