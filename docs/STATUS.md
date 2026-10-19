# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/bench-opx-streaming` (PR against `main`: the serial transport fix, the OPX streaming
report, L2-4 from the UI; the human merges). PRs #25–#71 merged 2026-10-14/19.
**Last session:** 2026-10-19, at the bench on wiring 1, after the OPX came back.
- **The OPX had moved to a self-assigned 169.254 address** (it had rebooted); the Mac's dock port had only a
  10.20 address, so the OPX answered ARP and mDNS but nothing else. Switching the port to DHCP (self-assigned
  169.254) fixed it without a password; the local stand file points at the new address. The cluster then
  reported "health not good enough" until the human attended to it. Nothing to do with the GitHub runner, which
  was queued because GitHub Actions was degraded (#71 was merged on local checks).
- **#67 proven on the OPX:** `bench/test_opx_streaming.py` passes; a 6 × 5 map with 40 ms shots delivered its
  rows 0.2 s apart while it ran (report).
- **L2-4 from the UI passes** (ADR 0066, 0067 on the bench): the capture kind, outer P1, scope2 read in the shot,
  pacing auto; "P1: triggered on dac_trigger"; plane fit `slope_row` 1.010 V/V, r² 1.000; the DAC holds +1.0 V
  after (readback and scope agree).
- **A serial-reply shift, found and fixed.** The first L2-4 attempt left the DAC at −0.5 V with the Levels widget
  showing −69 µV for P1. Cause: the SMU in the stand file was unreachable ("connection reset by peer"), so every
  Levels poll rebuilt all backends and closed them again, the QDAC's serial port threw, and from then on each
  query read the previous query's reply (the "setpoint" was `P1_i`'s current readout; `release` set P1 to P2's
  setpoint). `_VisaTransport` now discards pending input before every query (`test_scpi_transport.py`); the SMU
  is out of today's local stand file. The server's own handling of an unreachable instrument is a follow-up.
- **The SMU is back** in the local stand file; `qdt-server --stand` builds all four instruments; the server's
  Levels state reads every channel.
- **QDAC re-test for the QDevil report:** ch02, dead since 2026-10-15, works after the power cycle (±1 V on the
  scope within 2 %); the LOW sense range still measures nothing (±0.6 nA with 1 µA flowing). The report narrows
  to the LOW range and the filter; ch02 and the 0 V quirk are context.
- **L2-3 as one shot passes both ways** (wiring 2, the combiner board): the scope triggering itself on the
  analog edge, τ 1.82 µs; triggered by the OPX's marker (`trigger_from` on scope0), τ 1.81 µs; Probe 03's record
  gives 1.86 µs by the same fit. The shot form of ADR 0063 is proven on a real droop, in its interim and its
  marker variants.
- Earlier the same day (#71): the HD3's segmented transfer returns the selected segment repeated; the driver
  checks and falls back; the QDAC's output followed its setpoints (no 0 V quirk).

## Bench tasks — next bench session
1. ~~**The SMU**~~ — back in the stand file the same afternoon: it answered once its stale session had gone
   (five hardware conformance rows pass; the full four-instrument server builds with no error).
2. **The OPX's address:** decide whether to restore its static 10.20 address (its admin page) or keep the
   self-assigned one; the agent's bench notes cover both.
3. **The QDevil report** (drafted 2026-10-19, outside the repo because it carries the serial): the LOW
   current-sense range measuring nothing (re-tested 2026-10-19, still ±0.6 nA for any current) and the output
   filter having no effect on the step, with ch02's death-until-power-cycle and the outputs at 0 V after a
   power cycle until `*RST` as context. The human sends it.
Every bench row the software claims is now proven on its instrument: L1, L2-1 to L2-4, L2-3 as one shot, the
OPX's row streaming, the scope's segmented path, Probe 01–05.

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
- **2026-10-19:** #71 (the HD3's segmented transfer: `InfiniiVisionX.segments()` checks the block against
  segments read by index and falls back; the emulator's `all_segments="repeat"`); this branch: `_VisaTransport`
  discards pending input before every query (`test_scpi_transport.py`), the OPX streaming report, BENCH.md's
  OPX row and L2-4 note.
- On this branch: 456 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 20
  hardware-only in `bench/`; Flight Deck 137 unit tests and 14 e2e.

## In flight
- This PR awaits the human. On this laptop `qdt-server --stand` (the full bench stand) and Flight Deck's
  `pnpm dev` are still running from the session (ports 8700, 8765, 5173).
- **A stale `git am` in this checkout** (`.git/rebase-apply`, 2026-10-15: three "Claude (chat)" patches stopped
  at the third, about ADR 0050 and qdt-telemetry). It does not block commits. `git am --quit` removes it without
  touching any branch; `git am --abort` would move the current branch back, so not that.

## Known broken / not yet real
- **An instrument in the stand file that does not answer breaks every backend build** (the server rebuilds on
  each request and closes what it built): the server should build what it can, or remember the failure, instead
  of churning the others' connections. A follow-up slice.
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
**Human:** merge this PR; name the next slice. Candidates: the server
tolerating an unreachable instrument; a stimulus and a capture in the widget (L2-3 as one shot); the sequencer's
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
  unreachable); "typically I run a sudo command to expose the ip of the opx" (it was `sudo ifconfig
  en11 alias`, not the cause: the OPX had moved to a link-local address); "the gh runner seems stuck" (GitHub
  Actions degraded; #71 merged on local checks); "ok the opx should be good to go" (#67 proven, L2-4 from the UI); "the combiner board is wired up" (L2-3 as one
  shot, both ways); "is the qdevil report still needed?" (yes, narrowed: ch02 revived, the LOW range still dead).

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
