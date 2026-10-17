# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/readout-choices` (PR against `main`; it carries #65's two commits; the human merges). PRs
#25–#63 merged 2026-10-14/16.
**Last session:** 2026-10-16, software only. The human asked to start from the local branch and take in the two
open PRs where they made sense and did not clash. **#65 is taken** (a fast-forward: the stage builder refuses a
capture row while it pulses an axis, the server's rule since ADR 0060). **#64 is left out**: written before ADR
0066 merged, its widget decided from the stand when an axis may be triggered (ADR 0066 rejects that), it numbered
its ADR 0066, and it rewrote the lines #63 changed. Then, asked to "take the readout choices from 64", **ADR 0067**:
a DC sweep reads its sensor per point or in the shot (a one-measure shot on the sensor's sequencer, shots
averaged), a capture records per point or in the shot (a capture from the scope's sequencer's marker, start
pinned at 0, a wait after each record). #64's builders are reused; the widget checks only what the readout
needs (`sensorSequencer`, `captureSequencer`); the stepping preference applies to the innermost stepped axis of
any sweep with a shot, and the compiler still decides the pacing (ADR 0066). On the simulated stand a DC map and a
staircase built in the UI run with their axis triggered (e2e).

## Bench tasks — next bench session
1. **L2-3 as one shot** (`bench/test_l2_paced.py`): re-wire ao1 → combiner pulse in, QDAC ch01 →
   combiner DC in, board out → scope ch1; run first with the scope self-triggering (no `trigger_from` on
   scope0), then with the marker. Commit the report.
2. **A stability diagram through the UI on the bench**, to see ADR 0066 there: the plan box should say
   "P1: triggered on dac_trigger"; note that the OPX returns a triggered run's data only at the end (below).
   Then **L2-4 from the UI** (ADR 0067): the capture kind, outer P1, readout in the shot, QDAC ch01 on a scope
   input; the plan box should say "P1: triggered on dac_trigger".
3. **The QDevil report:** the three findings in BENCH.md plus the outputs at 0 V after a power cycle until
   `*RST`, seen twice.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0067. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064, its past-the-end semantics by 0065), stand/activity/pulse (0022; amended additively by
  0037, 0038, 0047, 0049, 0060, 0064; `stepping` made a preference and `ExecutionPlan.pacing` added by 0066),
  identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; 0048–0050, 0062), control (0036; 0046, 0050,
  0057). Registry DDL v3 (0026, 0029, 0050).
- **This session:** #65 taken (`stageSweep` refuses a capture row); ADR 0067: `readout` and `shot` on the DC and
  capture builders' forms, `sensorSequencer` and `captureSequencer`, the Sweep widget's readout select (the "in the
  shot" option disabled with its reason), the stepping select moved to the innermost stepped axis of any sweep with
  a shot ("software" not offered for a DC sweep read in the shot), the capture's start pinned at 0 in the shot,
  the next-run line marks "in the shot", the Pulse widget's note; `test/readout.test.ts`; an e2e flow for a DC map
  and a staircase read in the shot. No schema or server change.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 442 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 18
  hardware-only in `bench/`; Flight Deck 136 unit tests and 14 e2e.

## In flight
- Nothing uncommitted on the branch. PR for `step-6/readout-choices` awaits the human; **#64 is a superseded
  draft to close**; #65 can be merged first or closed as carried by this PR.
- **A local stash** on the bench laptop (`git stash list`: "wip: scope segments in one transfer") holds an
  uncommitted driver and emulator change for one transfer of all scope segments, with no tests yet; resume it
  for that slice or drop it.

## Known broken / not yet real
- **A DC sweep read in the shot needs its inner axis triggered** (ADR 0067): its stage has no axis of its own,
  so on a stand that cannot trigger the axis the compiler refuses with ADR 0066's message, and the widget does
  not offer "software" for it. Lifting the rule below makes it portable.
- **The widget offers only current channels as sensors**, so the OPX's voltage input is not a sensor in the UI
  and a DC sweep read in the shot cannot use it on the bench yet.
- **The widget builds no stage with a stimulus and no pulsed axis**: beyond the one-op shots of ADR 0067, the
  Pulse widget's capture row is refused in a stage sweep (with a message), so L2-3 as one shot (a step and a
  capture) is posted by hand.
- **On the OPX a triggered run's data arrive when the program ends** (the driver fetches once), so with
  "auto" a bench stability diagram's live view fills at the end instead of row by row. "software" in the
  Sweep widget is the override; streaming per row in the driver is the fix.
- **A stage with no axis of its own and one shot** records a once-per-point result only where the axis is
  triggered; host-stepped, the older rule (a stage result needs an axis or kept shots) applies and the
  compiler says so. Lifting that rule is a separate slice.
- **Timing now depends on the stand:** host stepping added a job submission per point that may have hidden
  a too-short `settle_s`; triggered, exactly the declared settle is waited. Check stand files' settles.
- **L2-3 as one shot is unrun** (the combiner is not wired).
- **Segment readout is 0.3–0.5 s each** over the socket; one transfer for all segments is a scope slice (its
  unfinished change is in the local stash above).
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
**Human:** merge this PR (it carries #65) and close #64; name the next slice. Candidates: the OPX streaming a
triggered run per row (it matters now that "auto" triggers on the bench); one transfer for all scope segments (the
stash); a stage result once per point with no stage axis (it would make a DC sweep read in the shot portable); a
stimulus and a capture in the widget (L2-3 as one shot); the sequencer's voltage inputs as sensors; the bench tasks
above; a second OPX pulse line; an OPX-ADC capture; how a sense range is declared; a rest level at a sweep's end; a
`tuneups`/`stand_state` table; resume and parallel branches. Step 7 when sign-off arrives.

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
  stepped control on the widget but postpone bench activites" (#64, superseded by ADR 0066 before review); "can
  you start fresh from the current local branch but incorporate the changes from the two open PRs if they make
  sense and don't clash?" (#65 taken, #64 left out); **"take the readout choices from 64"** (ADR 0067).

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
