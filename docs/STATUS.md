# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/bench-streaming-segments` (PR against `main`: a correctness fix for the scope driver and
today's bench report; the human merges). PRs #25–#70 merged 2026-10-14/18.
**Last session:** 2026-10-19, at the bench with wiring 1 (Probe 05's: OPX do1 → scope AUX TRIG IN, do2 → QDAC
ext1, QDAC ch01 → scope ch2 at 1 MΩ, OPX ao1 → scope ch1).
- **The QDAC is fine:** ch01 reads +0.500, −0.507 and −0.004 V on the scope for +0.5, −0.5 and 0 V set; the
  outputs-at-0-V quirk did not recur.
- **The scope's one transfer (#68) gave wrong records, and is fixed here.** The HD304MSO (firmware 10.16)
  accepts `:WAVeform:SEGMented:ALL ON` with no error, reads back 1, and returns a block of exactly records ×
  points, but the block holds the *selected* segment repeated, in RAW, NORMAL and MAXIMUM point modes alike
  (`:WAVeform:SEGMented:XLISt?` does list the ten distinct trigger times). On `main` the driver trusted the
  block, so every segmented capture on the bench would have returned one segment N times (L2-4 included).
  `bench/test_scope_segments.py` caught it on its first run. The driver now compares the block's first and last
  pieces with segments 1 and N read by index on the first segmented readout of a session and falls back to
  reading by index (0.30 s per segment on the HD3); the emulator models the HD3's answer
  (`all_segments="repeat"`); the bench test now passes, asserting the records equal the by-index reads.
- **The OPX did not answer** on its address (ARP incomplete on the dock's segment, while the scope on the same
  link did), so its streaming test (#67), L2-4 and L2-3 wait.

The previous sessions (2026-10-16/18) merged three slices: the OPX streams a run's results row by row (#67, not
yet run on the OPX); the scope's one-transfer readout (#68, fixed today); a stage records once per stepped
point without an axis of its own (ADR 0068, #69).

## Bench tasks — next bench session
1. **Bring the OPX back on the network** (power, its Ethernet to the switch, or its address), then
   **`bench/test_opx_streaming.py`** (the OPX alone, nothing cabled): #67's hardware check.
2. **L2-4 from the UI** (ADR 0067), on wiring 1: `qdt-server --stand` with the bench stand file; the capture
   kind, outer P1, capture channel scope2, readout in the shot. The plan box should say "P1: triggered on
   dac_trigger"; the five records must be the five levels (the fix above matters here). The L2-4 pytest row
   (`QDT_L2_STAIRCASE=1 QDT_L2_STAIRCASE_SCOPE_CHANNEL=2`) is the same check without the UI.
3. **L2-3 as one shot** (`bench/test_l2_paced.py`), on wiring 2: QDAC ch01 → combiner DC in, OPX ao1 → combiner
   pulse in, board out → scope ch1, do1 still on the scope's AUX TRIG IN, ground switches up. Run first with the
   scope self-triggering (no `trigger_from` on scope0 in the stand file), then with the marker.
4. **The QDevil report:** the three findings in BENCH.md plus the outputs at 0 V after a power cycle until
   `*RST`, seen twice (not on 2026-10-19).
A stability diagram through the UI cannot be built on this stand yet (the widget offers only current channels as
sensors, and the OPX's input is a voltage channel); L2-4 checks the same pacing.

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
- **2026-10-19:** `InfiniiVisionX.segments()` checks the one-transfer block against segments read by index and
  falls back; the emulator's `all_segments="repeat"`; an offline test of the HD3's answer; the bench test asserts
  the records whichever way they were read; BENCH.md's scope row; the bench report `2026-10-19-step6.md`.
- On this branch: 454 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 20
  hardware-only in `bench/`; Flight Deck 137 unit tests and 14 e2e.

## In flight
- This PR (the scope fix and the bench report) awaits the human. The simulated `qdt_server` and Flight Deck's
  `pnpm dev` from the 2026-10-19 demo may still be running on this laptop (ports 8700, 8765, 5173); stop the
  simulated server before `qdt-server --stand`.
- **A stale `git am` in this checkout** (`.git/rebase-apply`, 2026-10-15: three "Claude (chat)" patches stopped
  at the third, about ADR 0050 and qdt-telemetry). It does not block commits. `git am --quit` removes it without
  touching any branch; `git am --abort` would move the current branch back, so not that.

## Known broken / not yet real
- **The OPX's row streaming (#67) is unverified on hardware**: the OPX did not answer on 2026-10-19.
- **The HD3 cannot read its segments in one transfer** (firmware 10.16: `:WAVeform:SEGMented:ALL` repeats the
  selected segment), so segmented records are read by index, 0.30 s each.
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
**Human:** merge this PR (without it, a segmented capture on the bench returns one segment repeated); bring the OPX
back on the network and say "run the OPX tests" (the streaming test, then L2-4 from the UI); re-wire to wiring 2 for
L2-3; name the next slice. Candidates: a stimulus and a capture in the widget (L2-3 as one shot); the sequencer's
voltage inputs as sensors; streaming a 1-D OPX result; a second OPX pulse line; an OPX-ADC capture; how a sense
range is declared; a rest level at a sweep's end; a `tuneups`/`stand_state` table; resume and parallel branches.
Step 7 when sign-off arrives.

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
- **2026-10-19:** "walk me through a flight deck demo" (the simulated server and `pnpm dev`, a guided tour); "tell
  me how to wire up the bench"; "wiring one is set up" (the scope's one transfer caught and fixed; the OPX
  unreachable).

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
