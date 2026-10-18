# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/stage-result-per-point` (PR against `main`, stacked on #67; the human merges). Open: #67
(the OPX streams rows), #68 (the scope reads every segment in one transfer; its bench test first) and this one.
PRs #25–#66 merged 2026-10-14/16.
**Last session:** 2026-10-16/17, software only (the dock was unplugged throughout). The human asked for three
slices in this order:
1. **The OPX streams a run's results row by row** (#67): ADR 0015's chunking on the OPX. A result over two or more
   program axes arrives one slab of its first axis per frame, fetched as soon as every measure stream holds it
   (`count_so_far`, `fetch` by slice); a run that ends short raises; a 1-D result and the conformance program
   stay one fetch at the end. A triggered stability diagram's live view now fills row by row.
   `bench/test_opx_streaming.py` (the OPX alone) proves it on hardware; not yet run.
2. **The scope reads every segment in one transfer** (#68): `:WAVeform:SEGMented:ALL` and one `:WAVeform:DATA?`
   when the scope accepts the command (the error queue, read after `*CLS`) and the block holds records × the
   preamble's points; otherwise segment by segment, decided on the first segmented readout and kept. **Merge it
   only after `bench/test_scope_segments.py` passes** (the scope alone): it reads one acquisition both ways and
   compares.
3. **A stage records once per stepped point without an axis of its own** (ADR 0068, this branch): the program
   gets a one-point axis `once` (`n_once` = 1) and the slab a one-point dimension, which the executor strips;
   only a value with no axis anywhere is refused. A definition now compiles on any stand, triggered or stepped
   from the host; a DC sweep read in the shot runs host-stepped, and the widget offers "software" for it again.

## Bench tasks — next bench session (with the dock plugged in)
1. **`bench/test_opx_streaming.py`** (the OPX alone, nothing cabled): #67's hardware check.
2. **`bench/test_scope_segments.py`** (the scope alone): #68's gate. If the HD3 refuses
   `:WAVeform:SEGMented:ALL`, the driver keeps reading per segment and #68 only adds a test of what it lacks.
3. **L2-3 as one shot** (`bench/test_l2_paced.py`): re-wire ao1 → combiner pulse in, QDAC ch01 → combiner DC in,
   board out → scope ch1; run first with the scope self-triggering (no `trigger_from` on scope0), then with the
   marker. Commit the report.
4. **A stability diagram through the UI**: the plan box should say "P1: triggered on dac_trigger", and with #67
   the rows fill as the OPX runs. Then **L2-4 from the UI** (ADR 0067): the capture kind, outer P1, readout in
   the shot, QDAC ch01 on a scope input.
5. **The QDevil report:** the three findings in BENCH.md plus the outputs at 0 V after a power cycle until
   `*RST`, seen twice.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0068. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064, its past-the-end semantics by 0065), stand/activity/pulse (0022; amended additively by
  0037, 0038, 0047, 0049, 0060, 0064; `stepping` made a preference and `ExecutionPlan.pacing` added by 0066),
  identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; 0048–0050, 0062), control (0036; 0046, 0050,
  0057). Registry DDL v3 (0026, 0029, 0050). ADR 0068 changes no schema: `once` lives in the program and the
  slab only.
- **This session:** #67: `_RunSource` streams rows (`_wait_for_values`, `results(rows=)`), three offline OPX
  tests, `bench/test_opx_streaming.py`. #68: `segments()` and `segments_in_one_transfer` in `InfiniiVisionX`,
  the emulator's `:WAVeform:SEGMented:ALL`, `*CLS` and `:SYSTem:ERRor?`, four scope offline tests,
  `bench/test_scope_segments.py`. ADR 0068: `ONCE` and `once_results` in the emitter, the one-point axis,
  `stage_slab`'s one-point dimension, the executor strips it, compile refuses a value with no axis anywhere;
  tests in qdt-lab, qdt-sim (the model at each host-stepped point), the OPX offline suite and Flight Deck (unit,
  and an e2e host-stepped map read in the shot).
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- On this branch (with #67): 450 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in
  `packages/`, 19 hardware-only in `bench/`; Flight Deck 137 unit tests and 14 e2e. #68 adds four scope tests
  and one bench test.

## In flight
- Nothing uncommitted. Three PRs: #67, then this one (stacked on it); #68 after its bench test.
- **A stale `git am` in this checkout** (`.git/rebase-apply`, 2026-10-15: three "Claude (chat)" patches stopped
  at the third, about ADR 0050 and qdt-telemetry). It does not block commits. `git am --quit` removes it without
  touching any branch; `git am --abort` would move the current branch back, so not that.

## Known broken / not yet real
- **Unverified on hardware:** the OPX's row streaming (#67) and the scope's one transfer (#68); the two bench
  tests above prove them.
- **A 1-D OPX result still arrives at the end of the run** (ADR 0015 gives a 1-D result one frame), so a long
  triggered 1-D scan fills at once.
- **Stepped from the host, a stage with no axis of its own is one OPX job per point** (ADR 0068); triggered
  stays the fast way.
- **The widget offers only current channels as sensors**, so the OPX's voltage input is not a sensor in the UI
  and a DC sweep read in the shot cannot use it on the bench yet.
- **The widget builds no stage with a stimulus and no pulsed axis**: beyond the one-op shots of ADR 0067, the
  Pulse widget's capture row is refused in a stage sweep (with a message), so L2-3 as one shot (a step and a
  capture) is posted by hand.
- **Timing now depends on the stand:** host stepping added a job submission per point that may have hidden
  a too-short `settle_s`; triggered, exactly the declared settle is waited. Check stand files' settles.
- **L2-3 as one shot is unrun** (the combiner is not wired).
- **Until #68 merges, segments are read one by one**, 0.3–0.5 s each over the socket.
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
**Human:** merge #67, then this PR (stacked on it); plug the dock in and say "run the bench tests", so #67 is
proven on the OPX and #68 can merge after its scope test; name the next slice. Candidates: a stimulus and a
capture in the widget (L2-3 as one shot); the sequencer's voltage inputs as sensors; streaming a 1-D OPX
result; the bench tasks above; a second OPX pulse line; an OPX-ADC capture; how a sense range is declared; a
rest level at a sweep's end; a `tuneups`/`stand_state` table; resume and parallel branches. Step 7 when sign-off
arrives.

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
  sense and don't clash?" (#65 taken, #64 left out); **"take the readout choices from 64"** (ADR 0067); **"let's
  tackle everything on this list in this order"**: the OPX streaming rows (#67), one transfer for all scope
  segments (#68), a stage result once per point with no stage axis (ADR 0068).

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
