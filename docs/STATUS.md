# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6b — Flight Deck workspace → `docs/steps/06b-flightdeck-workspace.md` (IN PROGRESS, opened
2026-10-15 on the human's "go with 6b"; ADR 0054 accepted with it). Step 6 is DONE (closed 2026-10-15; its L3
confirmation is the first fridge task, below). Step 7 waits for manager sign-off.
**Branch:** `step-6b/shell` (PR against `main`; the human merges). PRs #25–#51 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6b session 1 (not at the bench). **The shell**, deliverable 1 of six. Themes
as data (`apps/flightdeck/themes/{slate,paper,steel}.json` + `theme.schema.json`, validated by
`workspace/theme.ts`; load/export/remember per browser; a closed flag list becomes `deco-*` classes; a theme
can never inject CSS). The top strip (stand, device, source, live pill, next-run line, one Run, telemetry,
progress, messages, replay picker, theme menu). The layout model (`workspace/layout.ts`, pure, tested), the
widget contract and registry with a bus scoped per mount (`widget.ts`), the typed bus (`bus.ts`), the renderer
(`workspace.ts`, panes reconciled by id, pointer + keyboard gutters). Widgets: `plot` (the old stage, one
instance, selects in its pane head), `control` (the Step 4b panel mounted unchanged), `empty`. `main.ts` is
wiring. No behaviour change: the six existing e2e tests pass untouched.

## Step 6b deliverables (step file; one session each)
| # | Deliverable | State |
|---|---|---|
| 1 | Shell: themes as data, strip, layout model, widget registry, bus; panel mounted unchanged | ✔ session 1 |
| 2 | Plot panes: N instances over the shared stores, ⚙ menu, follow-live or pinned; History widget | next |
| 3 | Sweep + Pulse widgets; Run moves to the strip, bound to the compiled plan with a stale marker | — |
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
- **Steps 0–6 DONE.** ADR 0001–0054. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021), stand/activity/pulse
  (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033;
  Step 6 objects beside it by 0048–0050), control (0036; amended additively by 0046; `TuneUp` beside it by
  0050). Registry DDL v3 (0026, 0029, 0050).
- **Step 6:** `qdt-tuning`; three nodes; virtual gates; the tune-up API; the held operating point and `/levels`;
  Flight Deck's Tune-up section and click-to-set.
- **Step 6b so far:** the shell (above). `e2e/workspace.test.ts`: default layout, theme on `:root`, split/close
  persisted across a reload, keyboard gutters, the theme menu.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 394 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 102 unit tests and 9 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/shell` awaits the human.

## Known broken / not yet real
- **One plot pane this session**: the `plot` widget is single-instance (its canvases and selects keep the ids the
  e2e tests drive), so the centre's `+` is disabled until deliverable 2. The right column starts with an `empty`
  pane because a column keeps its last pane; the only other widget is `control`, also single-instance.
- **The strip's Run and next-run line read the control panel's form** (the panel is unchanged): two Run
  controls until deliverable 3 binds the strip's to the compiled plan. The strip's stand/device come from the
  API; without a server they read "?".
- **No Google Fonts link**: the Plex stacks fall back to system fonts (the bench is offline); a theme may name any
  installed font.
- **A pane's widget keeps polling after close** only where the old panel does (`follow` loops end at a terminal
  state); the registry disposes bus subscriptions, not the panel's own timers.
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
**Sessions:** Step 6b deliverable 2, **plot panes**: `src/widgets/plot.ts` becomes N instances over the shared
`Datasets` (each its own `MapRenderer`, view options and cut cursor; follow-live or pinned to a dataset; the
selects move into a ⚙ head menu that is focus-trapped and closes on Escape), the WebGL2 context cap decided
(Open decisions: cap at ~6 or fall back to `cpu`), `src/widgets/history.ts` over `/records` with "shown in" and
open-in-plot; `render.test.ts` gains the two-panes source-equivalence check; the e2e ids (`#plot`, `#overlay`,
`#datasets`, …) become per-pane selectors and `control.test.ts` follows. Then deliverables 3–6 in order.

**Human:**
1. Merge the PR; look at the shell in `pnpm dev` (the theme menu, the gutters, split/close on the right column).
2. Say whether the strip's Run should already hide the panel's own run button (two Run controls until
   deliverable 3), and whether a Google Fonts link is wanted for online use.
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
  simulator, the L3 confirmation is the first fridge task; **"go with 6b"**: Step 6b opens, ADR 0054 is accepted,
  the shell is session 1.

## Decisions pending
- Step 6b's Open decisions (its file): layout as a schema object; the WebGL2 context cap; `/levels` readback
  semantics; the script sandbox; the release mirror's first widgets; themes per browser or in the registry.
- Two Run controls until deliverable 3; a Google Fonts link for online use.
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
