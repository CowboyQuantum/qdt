# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/sweep-stepping` (PR against `main`; the human merges). PRs #25–#62 merged 2026-10-14/16.
**Last session:** 2026-10-16 (not at the bench; the human postponed the bench tasks), **the Sweep widget's
stepping control** (ADR 0066), the follow-up ADR 0064 left. One "stepping" field below the axes applies to the
innermost stepped axis of the kind (a stage or capture sweep's outer axis, a DC sweep's inner one): "software:
set each point" or "triggered by the sequencer". It is offered only when the stand can trigger that axis
(`triggerFor`/`steppingFor` mirror the compiler: a list-capable DAC that is the sequencer or names a sequencer
channel as `trigger_from`; the DC sensor on that sequencer; the scope not on it); otherwise it is disabled and
the hint says why. A triggered axis moves the per-point readout into the shot: a stage sweep is unchanged; a DC
sweep reads the sensor in a one-measure shot (integration in ns, shots averaged); a capture becomes a capture op
in the shot from its marker (start pinned at 0), one record per shot, then a pacing wait (50 ms by default).
The stage builder now refuses a capture row while it pulses an axis, as the server did. On the simulator a
triggered DC map and a triggered staircase run through the server from the UI (e2e).

## Bench tasks — next bench session (postponed 2026-10-16)
1. **L2-3 as one shot** (`bench/test_l2_paced.py`): re-wire ao1 → combiner pulse in, QDAC ch01 →
   combiner DC in, board out → scope ch1 (the 2026-10-16 session had ao1 direct into the scope for
   Probe 05); run first with the scope self-triggering (no `trigger_from` on scope0), then with the
   marker. Commit the report.
2. **The QDevil report:** the three findings in BENCH.md plus 2026-10-16: outputs at 0 V after a power
   cycle until `*RST` (second time), ch02 not re-checked.
3. **A triggered sweep from Flight Deck at the bench** (ADR 0066): the staircase (capture kind, P1 triggered)
   and a DC map with the sensor on an OPX input, from the UI against `qdt-server --stand`.
4. Later: reading all segments in one transfer (readout is 0.3–0.5 s per segment); a second OPX pulse
   line; an OPX-ADC capture.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0066. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064, its past-the-end semantics by 0065), stand/activity/pulse (0022; amended additively by
  0037, 0038, 0047, 0049, 0060, 0064), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; 0048–0050,
  0062), control (0036; 0046, 0050, 0057). Registry DDL v3 (0026, 0029, 0050).
- **This session:** `control/sweeps.ts`: `AxisForm.stepping`, `triggerFor`, `steppingFor`, `companionErrors`;
  `dcSweep` and `captureSweep` build the in-shot readout when their axis is triggered; `stageSweep` refuses a
  capture row with a pulsed axis and never reduces a capture. `widgets/sweep.ts`: the stepping field, its
  hint, the integration and between-records fields, the pinned capture start; the next-run line and the plan
  summary name the triggered axis. The Pulse widget's note for DC and capture sweeps. Tests: 9 unit
  (`test/stepping.test.ts`), one e2e (a triggered DC map run to a heatmap, a triggered staircase run).
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 433 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 18
  hardware-only in `bench/`; Flight Deck 133 unit tests and 14 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/sweep-stepping` awaits the human.

## Known broken / not yet real
- **The widget builds no stage without a pulsed axis**: a stimulus plus a capture or measure per point (L2-3 as
  one shot) is posted by hand. The Pulse widget's capture row is refused in a stage sweep until then; the
  emitter also refuses a measure with no program axis unless shots are kept.
- **A triggered DC sweep reads the sensor through the sequencer's input**, not the meter's `LevelSense`; on
  the bench the sensor has to be an OPX input (the hint says so). The capture's pacing wait (50 ms) is the
  bench's value with segmented memory; 0.5 s without it (ADR 0065).
- **L2-3 as one shot is unrun** (the combiner is not wired); the self-trigger interim and the marker form
  are both untested on a real droop.
- **Segment readout is 0.3–0.5 s each** over the socket after the acquisition; one transfer for all segments
  is the next scope slice.
- **The LF-FEM's digital I/O adapter**: nothing in software can tell when it is off; BENCH.md says to check it.
- **The marker-to-analog delay (85 ns) is recorded, not applied**; a shot capture's record starts at the marker.
- **A triggered axis through the combiner's DC side is still 50 ms per point** (its 20 Hz low-pass).
- **`provenance_check.sh` matches bare substrings**; a word-boundary pattern is a one-line fix.
- Carry-overs unchanged: a retune needs a held level (0062); the fitted width is thermal only in linear
  response; the simulated sensor's neighbouring peaks bias the background; the UI's run queue has no
  reordering; the simulator's live device and a run's device diverge (0057); a simulated gate reads back
  null; the Levels widget polls; limits and the coupling matrix are per browser; Run compiles again when
  stale (0056); the Script widget runs nothing (0059); the held operating point is server memory; `TuneUp`
  not persisted, one at a time, no resume/parallel (0050); `detect_transitions` reports `ok` on a constant
  map; `SimScenario.model` overrides scalars only; QDAC-II quirks (BENCH.md); the trace view has no
  axes/labels/output curve; the exponential's edge detector is a heuristic (0046); the plane fit is OLS
  (0045); OPX input offset not applied; `bench_report.py` does not redact serials; qm-qua deprecations;
  zero-clipping in the dot model (0020); Postgres suite only in CI; `FINISH_LINE.md` TODO (human);
  Windows pnpm via `corepack pnpm`.

## Next action
**Human:** merge the PR; try the stepping field in `pnpm dev` against `python -m qdt_server` (a DC sweep with
P2 triggered, a capture with P1 triggered). Then name the next slice. Software candidates (no bench): a stage
without a pulsed axis in the widget (the Pulse widget's shot per point, L2-3's shape from the UI); how a sense
range is declared; a rest level at a sweep's end; a `tuneups`/`stand_state` table; resume and parallel
branches. Bench candidates (when the bench is back): the list above. Step 7 when sign-off arrives.

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
- **2026-10-14, tabled:** Flight Deck should visualise time-series data (scope records first). Partly done
  2026-10-15 (record traces draw as traces with markers).
- **2026-10-15:** the scope is L2-1's sink; waveform capture is a server feature (ADR 0047); Probe 04; finish the
  OPX conformance rows and L2-2 before closing Step 5; Step 5 closes and Step 6 opens; the schema slice and the
  first node first (ADR 0048); the second node is the virtual-gate stability diagram (ADR 0049); the persisted
  tune-up before a third node (ADR 0050); `qdt-telemetry` ingests, does not collect (ADR 0051); the third node is
  the sensor operating point (ADR 0052); click-to-set (ADR 0053); "let's strike the DAPS development for now";
  the Step 6b spec arrives as a chat patch (ADR 0054); "let's put off L3 and close step 6"; "go with 6b".
- **2026-10-16:** PRs #52–#57 merged without a word, so Step 6b's six sessions (ADR 0054–0059) followed the step
  file's order; "the flight deck ci didn't pass" (two timing fixes in #56); on `PlayedWaveform`: "perhaps we need
  to go back to how sweeps and pulse sequences (including readout) get composed", then "go ahead and revise the
  adr and implement": the shot is the timeline (ADR 0060); "let's clear up the other flight deck follow ups"
  (ADR 0061); "I want the analysis to naturally sit on the wing of the sensor peak for a retune" (ADR 0062);
  "Let's focus on bench tasks today"; on the trigger line: "I like this middle option for the shot definition,
  but would still be open to setting up any tests or code changes to allow an external scope to be triggered
  externally" (ADR 0063); "I want to have the ability to sweep the dac by default, and only sweep the opx in the
  case that I'm sweeping a pulse amplitude within a shot pulse sequence", with the DAC stepped by a trigger line
  from the sequencer (ADR 0064); "start the code work now and I'll set up the instruments and let you know when
  to run that probe"; then at the bench: "run the probe"; the digital I/O adapter screwed on; the QDAC's trigger
  moved to the right port (ADR 0065); **"let's make a stepped control on the widget but postpone bench
  activites"** (ADR 0066).

## Decisions pending
- **What follows** (the candidates above).
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- Step 6's Open decisions (its file): how a sense range is declared; a rest level at a sweep's end; the
  time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
