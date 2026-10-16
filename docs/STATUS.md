# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/sequencer-paces-the-bench` (PR against `main`; the human merges). PRs #25–#60 merged
2026-10-14/16.
**Last session:** 2026-10-16, two Step 6 open decisions, software only; the bench half is set up and waits
for the human's "run the probe". The human chose (a) the shot definition now with the scope triggering
itself, and the marker line as a stand setting on the same path (**ADR 0063**); (b) the DC source stepped
by default, advancing on a trigger line from the sequencer so the sequencer paces the whole scan
(**ADR 0064**). Delivered: `TriggeredLevelSource` beside the frozen five (`load`, `advance`, `release`);
`SweepAxis.stepping = "triggered"` (one innermost stepped axis, needs a stage with a sequence, nothing
sensed or captured per point; couplings loaded as lists); the emitter puts the triggered axis outermost in
the program; the OPX's `do<p>` ports are marker lines (digital-only elements, a 400 ns `marker` pulse), the
receiving instrument's `settings["trigger_from"]` names the line; the OPX driver runs a shot capture
(marker when the scope has a line, self-trigger otherwise) and plays the DAC's marker at the top of the
triggered loop with the channel's settle; the executor loads lists per program run, drains a shot capture
on a thread while the shots play (a real scope acquires only while read), re-keys records to
(point, shot), releases at the end; the QDAC-II list mode (`trigger_in`, bus by default; `*TRG` fires it)
with its emulator and the conformance row; the scope arms on EXT (NORMal) when it has a line; the
simulated device is its own trigger. **Probe 05** (`docs/probes/05-sequencer-trigger-lines.md`,
`bench/probes/probe05/sequencer_markers.py`) is specified and written, not run. `bench/test_l2_paced.py`:
L2-3 as one shot, L2-4 the triggered staircase; neither run.

## Bench tasks — next session at the bench (human sets up, agent runs)
1. **Power-cycle the QDAC-II; check ch01/ch02 at ±1 V on the scope and the LOW sense range at 0 V** (the
   2026-10-15 quirks; what came back changes the QDevil report).
2. **Probe 05**, wired as its doc says (ao1 → scope ch1 50 Ω; do1 → scope EXT TRIG IN; do2 → scope ch2
   1 MΩ, then → QDAC ext1; QDAC ch01 → scope ch3 1 MΩ). Fill its Findings; then set `trigger_level_v`,
   confirm or change `MARKER_NS`, decide the t = 0 offset, record the shot-rate floor, fix the QDAC list
   commands if the error queue says so, and record whether `init` moves the output before the first
   marker (if it does: the driver or the program must account for one point).
3. **`bench/test_l2_paced.py`** against `qdt-server --stand` with the OPX in the stand and the lines in the
   stand file (`docs/examples/example_stand/bench.stand.example.json` has the shape): L2-3 one shot
   (self-trigger first, then with `trigger_from` on the scope), then L2-4 with `QDT_L2_STAIRCASE=1` and the
   direct cable. Commit the report.
4. **The QDevil report** (three findings in BENCH.md plus what the power cycle showed).

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0064. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064), stand/activity/pulse (0022; amended additively by 0037, 0038, 0047, 0049, 0060;
  `SweepAxis.stepping` and the `triggered_level_source` capability by 0064), identity/envelope/
  `qdt-hdf5-v1` (0028), modeling (0033; Step 6 objects beside it by 0048–0050; 0062), control (0036;
  amended additively by 0046, 0050; `ChannelLevel` by 0057). Registry DDL v3 (0026, 0029, 0050).
- **This session:** ADR 0063 and 0064 as above; Probe 05 spec and script; `bench/test_l2_paced.py`;
  BENCH.md (marker lines, the scope's EXT setting, L2-3 one shot, L2-4); the example stand file with the
  lines; Flight Deck API/data types regenerated (its Sweep widget does not offer `stepping` yet).
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 432 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 18
  hardware-only in `bench/`; Flight Deck 124 unit tests and 13 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/sequencer-paces-the-bench` awaits the human. The bench half of
  both ADRs (Probe 05, the two L2 rows) is the next bench session.

## Known broken / not yet real
- **Everything hardware-side of ADR 0063/0064 is unproven:** the marker's level (`EXT_TRIGGER_LEVEL_V`
  1.0 V assumed), `MARKER_NS` 400 ns, the marker-to-analog delay (not offset anywhere yet), the scope's
  re-arm floor (`CAPTURE_ARM_GRACE_S` 50 ms assumed; a shot capture's sequence ends in a `wait` of
  300 ms in the bench rows), the QDAC-II list commands (the manual's; the error queue will say), and
  whether `init` plays point 0 before the first trigger. Probe 05 answers all five.
- **A shot capture through a real scope is one `:DIGitize` per record**: shots faster than the re-arm
  lose records and the drain times out (10 s VISA timeout). Segmented acquisition is the follow-on.
- **With the marker, a record starts at the capture op, after the stimulus op** (a 16 ns step is
  missed by 16 ns plus the delay); the self-trigger form sees the edge at t = 0. A pre-trigger baseline
  is not in the shot vocabulary.
- **A triggered axis through the combiner's DC side is still 50 ms per point** (its 20 Hz low-pass);
  sub-ms is real only direct into a high-impedance input.
- **Flight Deck's Sweep widget has no `stepping` control**; a triggered sweep is posted by hand or by a
  node. The simulated stand (`qdt-server` without `--stand`) runs it: the device is its own trigger.
- **`provenance_check.sh` matches bare substrings**; a word-boundary pattern is a one-line fix.
- Carry-overs unchanged from before: a retune needs a held level (0062); the fitted width is thermal only
  in linear response; the simulated sensor's neighbouring peaks bias the background; the UI's run queue
  has no reordering; the simulator's live device and a run's device diverge (0057); a simulated gate reads
  back null; the Levels widget polls; limits and the coupling matrix are per browser; Run compiles again
  when stale (0056); the Script widget runs nothing (0059); the held operating point is server memory;
  `TuneUp` not persisted, one at a time, no resume/parallel (0050); `detect_transitions` reports `ok` on a
  constant map; `SimScenario.model` overrides scalars only; QDAC-II quirks (BENCH.md); the trace view has
  no axes/labels/output curve; the exponential's edge detector is a heuristic (0046); the plane fit is OLS
  (0045); OPX input offset not applied; `bench_report.py` does not redact serials; qm-qua deprecations;
  zero-clipping in the dot model (0020); Postgres suite only in CI; `FINISH_LINE.md` TODO (human);
  Windows pnpm via `corepack pnpm`.

## Next action
**Human:** merge the PR; set the bench up as Probe 05's doc says; say "run the probe". **Then (agent, at
the bench):** the four bench tasks above in order, the probe's Findings table filled, the drivers' constants
set from it, the L2 rows run, the report committed, an ADR only if a finding changes a decision (a wrong
SCPI guess is a driver fix, not an ADR).

**After the bench:** the human names the next slice. Candidates: segmented acquisition on the scope; the
Sweep widget's `stepping`; a second OPX pulse line (ao2 → scope ch2; two lines in one shot, their skew);
an OPX-ADC capture (a capture on the sequencer's own input, Probe 02's loopback; short windows only);
how a sense range is declared; a rest level at a sweep's end; a `tuneups`/`stand_state` table; resume and
parallel branches. Step 7 when sign-off arrives.

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
  **"Let's focus on bench tasks today"**; on the trigger line: "I like this middle option for the shot
  definition, but would still be open to setting up any tests or code changes to allow an external scope to be
  triggered externally" (ADR 0063); "I want to have the ability to sweep the dac by default, and only sweep the
  opx in the case that I'm sweeping a pulse amplitude within a shot pulse sequence", with the DAC stepped by a
  trigger line from the sequencer (ADR 0064); "start the code work now and I'll set up the instruments and let
  you know when to run that probe".

## Decisions pending
- **Probe 05's findings** and what they change (above).
- **What follows** (the candidates above).
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- Step 6's Open decisions (its file): how a sense range is declared; a rest level at a sweep's end; the
  time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
