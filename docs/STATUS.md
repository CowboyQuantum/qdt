# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/stage-capture-guard` (PR against `main`; the human merges). PRs #25–#63 merged 2026-10-14/16.
**Last sessions:** 2026-10-16, two in parallel, software only.
- **ADR 0066, pacing is the plan's** (merged as #63). The human asked whether the Sweep widget was the right
  place for a stepping control and whether software versus hardware sweeps deserved a formal place in the code.
  They bundle two decisions: *what produces the level* (a DC line or a pulse in the shot: the axis's channel,
  the experiment's choice) and *who paces the DC steps* (the host or the sequencer's marker: the stand's
  wiring). The second is now the plan's: `resolve_pacing` in `qdt_lab.experiment` decides from the stand;
  `ExecutionPlan.pacing` records one `AxisPacing` per axis (`software`, `triggered` with its marker lines,
  `sequencer`) and the Dataset attrs carry `<axis>.pacing`; `SweepAxis.stepping` is a preference, default
  "auto" ("triggered" required, "software" forced); the executor reads the plan. The Sweep widget shows the
  per-axis pacing in its plan box and has an "outer stepping" select for stage sweeps. On the simulated stand
  "auto" triggers the DC axis (the device is its own sequencer); data are identical to host stepping.
- **A stepping control in the Sweep widget** (#64, now a draft, superseded). Asked for in the other session
  ("let's make a stepped control on the widget but postpone bench activites"), it was built as a user's choice
  on the innermost stepped axis, the widget mirroring the compiler's wiring rules, with a DC sweep's sensor and
  a capture's record moved into the shot when triggered. #63 merged first and ADR 0066 rejects deciding in the
  widget from the stand, so #64 should be closed. One fix it found holds on main and is this branch: **the stage
  builder refuses a capture row while it pulses an axis** (the server's rule since ADR 0060; the builder used to
  send the definition and main's unit test asserted it), so the error shows while the row is typed.

## Bench tasks — next bench session
1. **L2-3 as one shot** (`bench/test_l2_paced.py`): re-wire ao1 → combiner pulse in, QDAC ch01 →
   combiner DC in, board out → scope ch1; run first with the scope self-triggering (no `trigger_from` on
   scope0), then with the marker. Commit the report.
2. **A stability diagram through the UI on the bench**, to see ADR 0066 there: the plan box should say
   "P1: triggered on dac_trigger"; note that the OPX returns a triggered run's data only at the end (below).
3. **The QDevil report:** the three findings in BENCH.md plus the outputs at 0 V after a power cycle until
   `*RST`, seen twice.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0066. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064, its past-the-end semantics by 0065), stand/activity/pulse (0022; amended additively by
  0037, 0038, 0047, 0049, 0060, 0064; `stepping` made a preference and `ExecutionPlan.pacing` added by 0066),
  identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; 0048–0050, 0062), control (0036; 0046, 0050,
  0057). Registry DDL v3 (0026, 0029, 0050).
- **ADR 0066's session:** ADR 0066 (ADR 0064's status line marks the partial supersession); `resolve_pacing`;
  `AxisPacing` and `ExecutionPlan.pacing` with a consistency validator and `pacing_of` / `triggered_axis` /
  `program_axes` / `software_axes` (the definition's helpers moved to the plan); the compiler explains a
  once-per-point result on a host-stepped axis; the Sweep widget's plan box and stepping select; the Step 6
  file's Probe 05 note.
- **This branch:** `stageSweep` refuses a capture row (it always pulses an axis); `test/sequence.test.ts`'s
  capture test checks the refusal instead of the definition the server refused.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 442 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 18
  hardware-only in `bench/`; Flight Deck 127 unit tests and 13 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/stage-capture-guard` awaits the human; **#64 is a superseded draft to close**.

## Known broken / not yet real
- **The Sweep widget cannot build a triggered DC × DC map or a staircase.** Under ADR 0066 a triggered axis
  needs its readout in the shot, and only the stage kind has a shot, always with a pulsed axis. The useful
  remainder of #64 is a *readout* choice, not a pacing one: "read in the shot" for a DC sweep (the sequencer
  integrates the sensor in a one-measure shot) and "record in the shot" for a capture (a capture op from its
  marker, then a pacing wait); "auto" pacing would then trigger them on a wired stand. #64's builders for both
  can be reused if the human wants this.
- **The widget builds no stage without a pulsed axis**, so the Pulse widget's capture row is refused in a stage
  sweep (now with a message); a stimulus plus a capture per point (L2-3 as one shot) is posted by hand.
- **On the OPX a triggered run's data arrive when the program ends** (the driver fetches once), so with
  "auto" a bench stability diagram's live view fills at the end instead of row by row. "software" in the
  Sweep widget is the override; streaming per row in the driver is the fix.
- **A stage with no axis of its own and one shot** records a once-per-point result only where the axis is
  triggered; host-stepped, the older rule (a stage result needs an axis or kept shots) applies and the
  compiler says so. Lifting that rule is a separate slice.
- **Timing now depends on the stand:** host stepping added a job submission per point that may have hidden
  a too-short `settle_s`; triggered, exactly the declared settle is waited. Check stand files' settles.
- **L2-3 as one shot is unrun** (the combiner is not wired).
- **Segment readout is 0.3–0.5 s each** over the socket; one transfer for all segments is a scope slice.
- **The LF-FEM's digital I/O adapter**: nothing in software can tell when it is off; BENCH.md says to check.
- **The marker-to-analog delay (85 ns) is recorded, not applied.**
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
**Human:** merge this PR and close #64. Then say whether the Sweep widget should get the readout choices
("read in the shot" for a DC sweep, "record in the shot" for a capture) so that "auto" pacing can trigger a DC
map and a staircase built in the UI; or name another slice. Candidates: the OPX streaming a triggered run per
row (it matters now that "auto" triggers on the bench); one transfer for all scope segments; a stage result
once per point with no stage axis; the bench tasks above; a second OPX pulse line; an OPX-ADC capture; how a
sense range is declared; a rest level at a sweep's end; a `tuneups`/`stand_state` table; resume and parallel
branches. Step 7 when sign-off arrives.

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
  to run that probe"; at the bench: "run the probe"; the digital I/O adapter screwed on; the QDAC's trigger moved
  to the right port (ADR 0065); on the stepping control: "Is this the right place to put this? I'm wondering if
  it's worth formalizing a software sweep versus a hardware sweep in the code", then **"do this"** to the
  recommendation that the stand decides and the plan records it (ADR 0066); in a parallel session, "let's make a
  stepped control on the widget but postpone bench activites" (#64, superseded by ADR 0066 before review).

## Decisions pending
- **What follows** (the candidates above), including the readout choices for DC and capture sweeps.
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- Step 6's Open decisions (its file): how a sense range is declared; a rest level at a sweep's end; the
  time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
