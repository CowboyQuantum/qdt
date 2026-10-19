# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/opx-input-sink` (PR against `main`: the OPX's input as the sink, ADR 0069; the human
merges). PRs #25–#72 merged 2026-10-14/19.
**Last session:** 2026-10-19 (session 24), at the bench, after #72 merged.
- **Bench housekeeping closed:** the SMU is back in the stand file (its conformance rows pass; the
  four-instrument server builds clean). The OPX's address and the QDevil report are the human's (below).
- **The OPX's input is a sink (ADR 0069), both halves proven on the bench (L2-5, `bench/test_l2_sensor.py`):**
  - a sequencer's voltage input is a sensor: the Sweep and Pulse widgets offer it (a voltage channel of a
    sequencer that sets no level, neither a `_pulse` line nor a marker line named in a `trigger_from`), read in
    the shot only (per point needs a meter: the compiler refuses by capability name, the widget disables the
    choice), result `V_sensor`; marker lines are offered nowhere. On the bench a DC map read by LF-FEM ai1 gives
    0.498 V/V against the 50 Ω-into-50 Ω half, triggered through `dac_trigger` and stepped from the host alike;
  - a capture on the sequencer's own input is a program result with its own time axis (`n_<result>` = num): the
    executor arms nothing, the OPX saves the raw ADC trace per shot from a readout pulse of the window's length
    on the input element, the simulated device records its sensor current over the window. On the bench L2-4's
    staircase recorded on the input gives the plane the scope gave, halved (0.498 V/V, flat in time).
- **Found on the bench:** the cable on ai1 carries QDAC ch01 (`P1`), not ch02: the first run read a flat map in
  P2 and the halved P1 along the other axis. `QDT_L2_SENSOR_CHANNEL` names the cabled channel.
- **Churn, again:** a killed server left the scope mid-`:SINGle` (a device clear over VXI-11 fixed it, per the
  agent's bench notes), and the Flight Deck page still open in the browser polled `/levels/state` against a
  stand whose scope build timed out, opening the QDAC's serial port twelve times over. The unreachable-instrument
  slice is overdue.

## Bench tasks — next bench session
1. **The OPX's address:** decide whether to restore its static 10.20 address (its admin page) or keep the
   self-assigned one. The agent recommends keeping it: the scope and the SMU live on 169.254 too, and the dock
   port reaches all three on DHCP with no password; the stand file and the agent's bench notes point there.
2. **The QDevil report** (drafted 2026-10-19, outside the repo because it carries the serial): the LOW
   current-sense range measuring nothing (±0.6 nA for any current) and the output filter having no effect on
   the step, with ch02's death-until-power-cycle and the outputs at 0 V after a power cycle until `*RST` as
   context. The human sends it, with `bench/probes/probe04/qdac_settling.py` and `bench/fixtures/probe04/`.
3. **A time-resolved signal on the OPX's input:** move the combiner board's output (or tee it) from scope ch1 to
   LF-FEM ai1 and run L2-3's one-shot step response captured on the input (the capture kind, channel `sensor`,
   in the shot); the 50 Ω load changes the droop, so the oracle is the board into 50 Ω, which Probe 03 did not
   measure: record it as a probe first.
4. **A second OPX pulse line:** ao2 to scope ch3; a two-line shot's skew (the emitter/widget slice comes first).
Every bench row the software claims is proven on its instrument: L1, L2-1 to L2-5, L2-3 as one shot, the OPX's
row streaming, the scope's segmented path, Probe 01–05.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0069. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064, its past-the-end semantics by 0065), stand/activity/pulse (0022; amended additively by
  0037, 0038, 0047, 0049, 0060, 0064; `stepping` made a preference and `ExecutionPlan.pacing` added by 0066),
  identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; 0048–0050, 0062), control (0036; 0046, 0050,
  0057). Registry DDL v3 (0026, 0029, 0050). ADR 0068 and 0069 change no schema: `once` and a record's
  `n_<result>` live in the program and the slab only.
- **This session:** ADR 0069. `standChannels` classifies a sequencer's inputs as sensors (and waveforms) and
  drops marker lines; `sensorPerPoint`, `sensorResult`; `buildSequence`/`newRow` take the stand's sensors; the
  Pulse widget's measure rows list them; the Sweep widget disables per point for them and names `V_sensor`.
  The emitter declares `n_<result>` and a result for a capture on the sequencer's own input; the compiler
  resolves it as a sequencer channel and declares its variable once; the stage slab carries its time dimension;
  the executor arms nothing for it; `Opx1000` records it as a readout pulse saving the raw ADC trace per shot
  (`_window_ns`, `_adc_stream`, `_measure_adc`; `plan["captures"]`; `_RunSource` scales and grids it);
  `SimulatedDevice` records its sensor current over the window (`read(..., overhead_s=0)`). Tests in qdt-lab
  (compile, run, the OPX offline suite), qdt-sim and Flight Deck; `bench/test_l2_sensor.py` (four rows).
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- **2026-10-19:** #71 (the HD3's segmented transfer), #72 (`_VisaTransport` discards pending input before every
  query, the OPX streaming report, BENCH.md's OPX row and L2-4 note, the SMU back), this branch (above).
- On this branch: 460 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 24
  hardware-only in `bench/`; Flight Deck 140 unit tests and 14 e2e.

## In flight
- This PR awaits the human. On this laptop `qdt-server --stand` (the full bench stand) is still running from the
  session (ports 8700, 8765); Flight Deck's dev server is stopped, but a Flight Deck tab may still be open in
  the browser, polling the server's levels.
- **A stale `git am` in this checkout** (`.git/rebase-apply`, 2026-10-15: three "Claude (chat)" patches stopped
  at the third, about ADR 0050 and qdt-telemetry). It does not block commits. `git am --quit` removes it without
  touching any branch; `git am --abort` would move the current branch back, so not that.

## Known broken / not yet real
- **An instrument in the stand file that does not answer breaks every backend build** (the server rebuilds on
  each request and closes what it built): the server should build what it can, or remember the failure, instead
  of churning the others' connections. Bit twice on 2026-10-19 (the SMU in the morning, the scope after a
  kill). The follow-up slice, first in line.
- **`bench_report.py` names its file by `bench_step` in `pyproject.toml`, still "5"**: two runs today landed in
  a step-5 file and were moved by hand; bump the ini or pass `-o bench_step=6`.
- **The HD3 cannot read its segments in one transfer** (firmware 10.16: `:WAVeform:SEGMented:ALL` repeats the
  selected segment), so segmented records are read by index, 0.30 s each.
- **A 1-D OPX result still arrives at the end of the run** (ADR 0015 gives a 1-D result one frame), so a long
  triggered 1-D scan fills at once, a staircase recorded on the input included.
- **Stepped from the host, a stage with no axis of its own is one OPX job per point** (ADR 0068); triggered
  stays the fast way.
- **A capture in the shot still needs a stage without stage axes** (ADR 0060's rule, kept by ADR 0069): with the
  sequencer recording its own input a pulsed inner axis would be expressible; the validator cannot know the
  stand.
- **The widget's sensor classification is by convention** (`_pulse`, `trigger_from`): a sequencer output not
  named `_pulse` is offered as a sensor and refused at compile ("is an ao, not an ai").
- **The widget builds no stage with a stimulus and no pulsed axis**: beyond the one-op shots of ADR 0067, the
  Pulse widget's capture row is refused in a stage sweep (with a message), so L2-3 as one shot (a step and a
  capture) is posted by hand.
- **Timing now depends on the stand:** host stepping added a job submission per point that may have hidden
  a too-short `settle_s`; triggered, exactly the declared settle is waited. Check stand files' settles.
- **The LF-FEM's digital I/O adapter**: nothing in software can tell when it is off; BENCH.md says to check.
- **The marker-to-analog delay (85 ns) is recorded, not applied** (it does not apply to a capture on the OPX's
  own input, which plays no marker).
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
**Human:** merge this PR; name the next slice. Candidates: the server tolerating an unreachable instrument
(first: it bit twice today); a stimulus and a capture in the widget (L2-3 as one shot from the UI, now on the
OPX's input too); streaming a 1-D OPX result; a second OPX pulse line; an own capture with a stage axis; how a
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
  stepped control on the widget but postpone bench activites" (#64, superseded by ADR 0066 before review); "can
  you start fresh from the current local branch but incorporate the changes from the two open PRs if they make
  sense and don't clash?" (#65 taken, #64 left out); **"take the readout choices from 64"** (ADR 0067); **"let's
  tackle everything on this list in this order"**: the OPX streaming rows (#67), one transfer for all scope
  segments (#68), a stage result once per point with no stage axis (ADR 0068).
- **2026-10-19:** "walk me through a flight deck demo" (the simulated server and `pnpm dev`, a guided tour); "tell
  me how to wire up the bench"; "wiring one is set up" (the scope's one transfer caught and fixed; the OPX
  unreachable); "typically I run a sudo command to expose the ip of the opx" (it was `sudo ifconfig
  en11 alias`, not the cause: the OPX had moved to a link-local address); "the gh runner seems stuck" (GitHub
  Actions degraded; #71 merged on local checks); "ok the opx should be good to go" (#67 proven, L2-4 from the UI); "the combiner board is wired up" (L2-3 as one
  shot, both ways); "is the qdevil report still needed?" (yes, narrowed: ch02 revived, the LOW range still dead).
- **2026-10-19 (session 24):** "lets do all the bench things today" (the SMU back in the stand; the OPX's address
  and the QDevil report left to the human); "you can stop the server now, what other bench tests can I set up
  right now" (the list in the bench tasks); **"let's do (2), it's wired for that now"** (the OPX's input as the
  sink: a sequencer's voltage input is a sensor, a capture on it is a program result, ADR 0069).

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
- Whether a capture in the shot may have a stage axis when the sequencer records its own input (ADR 0069 keeps
  ADR 0060's rule; the validator cannot know the stand).
