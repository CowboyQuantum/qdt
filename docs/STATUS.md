# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6b — Flight Deck workspace → `docs/steps/06b-flightdeck-workspace.md` (IN PROGRESS, opened
2026-10-15). Step 6 is DONE (closed 2026-10-15; its L3 confirmation is the first fridge task, below). Step 7
waits for manager sign-off.
**Branch:** `step-6b/levels-gates` (PR against `main`; the human merges). PRs #25–#54 merged 2026-10-14/16.
**Last session:** 2026-10-16, Step 6b session 4 (not at the bench). **The Levels and Virtual gates widgets**,
deliverable 4 of six (ADR 0057). Server first: `ChannelLevel` (control slice, additive) and `GET /levels/state`,
every level-setting or level-sensing channel's setpoint, held level and readback, null where the instrument
refuses the channel (the simulated device senses its sensor, never a gate); the `RunManager` keeps one live
instrument set so a level set now is read back later and the sensor readback follows the gates. The Levels
widget: the table, filters (type, instrument, text, pinned, near-limit; AND across, OR within), sort, pins,
inline set with a limit refusal (±1 per browser) and a settling badge, release; click-to-set lands here (the
plot's `map:click` is offered as levels; the panel's section is gone). The Virtual gates widget: a coupling
matrix per browser; the Sweep widget gives each stepped axis its row as `SweepAxis.couplings` (ADR 0049); the
pure builder refuses couplings on a stage inner axis. Default layout sweep + control | plot | pulse + levels +
history (`flightdeck.layout.v3`). Pending human decisions were taken with the stated defaults: readback null
(not omitted), the limit a browser setting (no `ChannelMap` field).

## Step 6b deliverables (step file; one session each)
| # | Deliverable | State |
|---|---|---|
| 1 | Shell: themes as data, strip, layout model, widget registry, bus; panel mounted unchanged | ✔ session 1 (ADR 0054) |
| 2 | Plot panes: N instances over the shared stores, ⚙ menu, follow-live or pinned; History widget | ✔ session 2 (ADR 0055) |
| 3 | Sweep + Pulse widgets; Run moves to the strip, bound to the compiled plan with a stale marker | ✔ session 3 (ADR 0056) |
| 4 | Levels (operating point) widget with readbacks (`GET /levels/state`); Virtual gates widget | ✔ session 4 (ADR 0057) |
| 5 | Methods + Tune-up widgets; `panel.ts` deleted; `e2e/control.test.ts` migrated | next |
| 6 | Script widget placeholder | — |

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 DONE.** ADR 0001–0057. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021), stand/activity/pulse
  (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033;
  Step 6 objects beside it by 0048–0050), control (0036; amended additively by 0046, 0050; `ChannelLevel` beside
  it by 0057). Registry DDL v3 (0026, 0029, 0050).
- **Step 6:** `qdt-tuning`; three nodes; virtual gates; the tune-up API; the held operating point and `/levels`;
  Flight Deck's Tune-up section and click-to-set.
- **Step 6b so far:** the shell (1); plot panes and History (2); Sweep and Pulse, one Run (3); Levels and
  Virtual gates (4). Widgets: `plot`, `sweep`, `pulse`, `levels`, `gates`, `history`, `control` (records,
  analysis, tune-up), `empty`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 395 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 116 unit tests and 9 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/levels-gates` awaits the human.

## Known broken / not yet real
- **The simulator's live device and a run's device diverge**: the live set (operating point, readbacks) is
  built once; a run builds its own seeded device and leaves its last level there, not on the live one. On
  hardware they are the same objects. A readback on a simulated gate is null (the device senses only its sensor).
- **The Levels widget polls every 2 s**; on hardware each poll senses every sensable channel, honouring
  integration times. The interval is the widget's and can grow; nothing pushes channel state.
- **Limits are a browser setting** (±1, editable), not the stand's; a `ChannelMap` limit field is an additive
  change for the day a stand declares one.
- **The coupling matrix is per browser**; the tune-up's `virtual_gates` outputs are not pulled into it yet.
- **A stage sweep needs the Pulse widget mounted**; **one run at a time from the UI**; **Run compiles again when
  stale** (ADR 0056).
- **No colormap in the ⚙ menu**; **per-pane view state does not survive a reload** (ADR 0055).
- **The panel's Records list and "show" duplicate History** until deliverable 5. The strip's stand/device come
  from the API; without a server they read "?".
- **No Google Fonts link**; **`provenance_check.sh` matches bare substrings**.
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
**Sessions:** Step 6b deliverable 5, **Methods + Tune-up widgets; `panel.ts` deleted**: `src/widgets/analysis.ts`
(pick a record from History or the plot's pinned record, a method from `GET /methods`, its parameters, run it,
show the estimates, put the overlays and the output on the stream) and `src/widgets/tuneup.ts` (the nodes from
`GET /nodes`, options, start/stop, the DAG state rendered from `TuneUp`, ADR 0050); the records list is History's
("analyse" becomes History's per-row action or the Analysis widget's record picker). Then `control/panel.ts`,
`widgets/control.ts` and the `#control` styles go; `e2e/control.test.ts` drives the widgets only. Then
deliverable 6, the Script widget placeholder, and the step's exit criteria check.

**Human:**
1. Merge the PR; try the Levels widget (set, limit, release, click the map) and the Virtual gates matrix with a DC
   sweep in `pnpm dev` against `python -m qdt_server`.
2. Say whether the two defaults taken here stand (readback null; the limit a browser setting) or want an ADR
   amendment.
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
  the shell is session 1; PRs #52–#54 merged without a word, so sessions 2–4 (ADR 0055–0057) followed the step
  file's order, taking STATUS's stated defaults where a decision was pending.

## Decisions pending
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- A Google Fonts link for online use; a colormap choice (renderer slice); queueing a second run from the UI;
  pulling the tune-up's `virtual_gates` outputs into the coupling matrix.
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
