# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6b/follow-ups` (PR against `main`; the human merges). PRs #25–#58 merged 2026-10-14/16.
**Last session:** 2026-10-16, Flight Deck follow-ups (not at the bench), on the human's "let's clear up the other
flight deck follow ups" (ADR 0061). **Colormaps** `viridis`/`magma`/`grey` as a per-pane view setting: viridis keeps
its polynomial (the pixel oracle), the others are a 256-entry LUT both renderers read alike; the pixel e2e runs
every renderer × colormap against the CPU reference. **A pane remembers its view** across a reload (`Pane.state`
in the layout; the plot keeps variable, minus, transform, swap, cut, colormap; never a dataset id). **Web fonts**
are a per-browser opt-in in the theme menu, off by default. **The UI queues runs**: the server executes one at a
time; Run is never refused; the strip shows the executing run and how many wait; abort takes the running one.
**A tune-up's `c_21`/`c_12`** are offered to the Virtual gates widget with the gates they couple, applied on one
click, never unasked. **The record a plot pane shows** is a choice in the Analysis picker.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0061. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038, 0047, 0049, 0060), identity/envelope/
  `qdt-hdf5-v1` (0028), modeling (0033; Step 6 objects beside it by 0048–0050), control (0036; amended
  additively by 0046, 0050; `ChannelLevel` beside it by 0057). Registry DDL v3 (0026, 0029, 0050).
- **Step 6b:** the workspace (0054–0059) and its follow-ups (0061). **ADR 0060:** the shot is the timeline; a
  `capture` op; no `PlayedWaveform`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 401 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 124 unit tests and 13 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/follow-ups` awaits the human.

## Known broken / not yet real
- **Magma is nine anchors, linear between**: close to matplotlib's, not its curve; a fit like viridis's when
  someone needs the reference. No diverging colormap yet (a derivative would want one).
- **A shot capture runs on the simulator only** (ADR 0060): the sequencer-to-scope trigger is not in the
  protocols; the OPX driver refuses a `capture` op; on the bench L2-3 stays the per-point capture. A capture on
  the sequencer's own input is refused at compile; a shot capture allows no stage axes; the simulated scope's
  record does not depend on the stimulus.
- **The UI's run queue has no reordering**: the server has none.
- Flight Deck carry-overs: the simulator's live device and a run's device diverge (0057); a simulated gate reads
  back null; the Levels widget polls; limits and the coupling matrix are per browser; a stage sweep needs the
  Pulse widget mounted; Run compiles again when stale (0056); the Script widget runs nothing (0059); the strip's
  stand/device read "?" without a server.
- **`provenance_check.sh` matches bare substrings**; a word-boundary pattern is a one-line fix.
- Step 6 carry-overs: the held operating point is server memory (a `stand_state` table later); click-to-set only
  for axes named after stand DC channels; `flank_offset_v` is a judgment (0052); the diamonds method needs a cold
  sensor (0030); `TuneUp` not persisted, one at a time, no resume/parallel (0050); the bench has one OPX pulse
  line and no `SG`/`bias`/`sensor`; `detect_transitions` reports `ok` on a constant map; `SimScenario.model`
  overrides scalars only; QDAC-II quirks (BENCH.md); captures sequential; the trace view has no axes/labels/
  output curve; the exponential's edge detector is a heuristic (0046); the plane fit is OLS (0045); OPX input
  offset not applied; `bench_report.py` does not redact serials; qm-qua deprecations; zero-clipping in the dot
  model (0020); Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm via `corepack pnpm`.

## Next action
**Human:**
1. Merge the PR; try the ⚙ menu's colormap, a reload, two Runs in a row, and a tune-up's "apply" in the Virtual
   gates widget in `pnpm dev` against `python -m qdt_server`.
2. **Name the next slice.** The bench slices ADR 0060 opened: the sequencer-to-scope trigger line (protocol +
   stand + OPX driver) or a capture on the OPX's own ADC. The other Step 6 open decisions: sub-ms stepping; how
   a sense range is declared; a rest level at a sweep's end. A `sensor_peak` method. A bench session (second OPX
   pulse line, the QDevil report). Step 7 when sign-off arrives.

**Then (sessions):** the chosen item, on its own branch, with its ADR. A `tuneups` table and a `stand_state`
table when something reads them; resume and parallel branches when a DAG needs them.

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
  the Step 6b spec arrives as a chat patch (ADR 0054); "let's put off L3 and close step 6"; "go with 6b".
- **2026-10-16:** PRs #52–#57 merged without a word, so Step 6b's six sessions (ADR 0054–0059) followed the step
  file's order; "the flight deck ci didn't pass" (two timing fixes in #56); on `PlayedWaveform`: "perhaps we need
  to go back to how sweeps and pulse sequences (including readout) get composed", then "go ahead and revise the
  adr and implement": the shot is the timeline (ADR 0060); **"let's clear up the other flight deck follow ups"**
  (ADR 0061).

## Decisions pending
- **What follows** (the list above).
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- Step 6's Open decisions (its file): sub-ms stepping; how a sense range is declared; a rest level at a sweep's
  end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
