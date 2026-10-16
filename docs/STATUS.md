# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. Steps 0–6 and 6b are DONE. **Step 7 waits for manager sign-off**; between
steps, the human picks slices from the open decisions.
**Branch:** `step-6/probe-05` (PR against `main`; the human merges). PRs #25–#61 merged 2026-10-14/16.
**Last session:** 2026-10-16, at the bench: **Probe 05** (`docs/probes/05-sequencer-trigger-lines.md`) and
**ADR 0065**. The OPX's marker lines are real (3.27 V, 401 ns, 85 ns ahead of the analog edge) once the
LF-FEM's digital I/O adapter is screwed on; the scope's AUX TRIG IN fires on them; the QDAC-II's list
advances one point per marker on ext1 (5/5, three repeats, latency under 0.2 ms) once armed with
`dc:init:cont on`, and restarts past its end. The scope driver now acquires by `:SINGle` + `:AER?` +
`:RSTate?` with **segmented memory** for several records (10/10 records down to 20 ms apart; one
`:DIGitize` per record cost 0.45 s and lost markers, and a `:DIGitize` left waiting wedged the scope until
a HiSLIP device clear). **L2-4, the triggered staircase, passes through `qdt-server --stand`**
(`bench/reports/2026-10-16-step6.md`): five records at their levels, 4 s, the DAC holding its last point.
QDAC-II after its power cycle: outputs at 0 V with the setpoint reported, again; `*RST` fixed it.

## Bench tasks — next bench session
1. **L2-3 as one shot** (`bench/test_l2_paced.py`): re-wire ao1 → combiner pulse in, QDAC ch01 →
   combiner DC in, board out → scope ch1 (the 2026-10-16 session had ao1 direct into the scope for
   Probe 05); run first with the scope self-triggering (no `trigger_from` on scope0), then with the
   marker. Commit the report.
2. **The QDevil report:** the three findings in BENCH.md plus 2026-10-16: outputs at 0 V after a power
   cycle until `*RST` (second time), ch02 not re-checked this session.
3. Later: reading all segments in one transfer (readout is 0.3–0.5 s per segment); a second OPX pulse
   line; an OPX-ADC capture.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. The four-node tune-up on a real device through `POST /tuneups`; compare outcomes to the sim's.
2. The diamond estimator on a cold sensor (ADR 0030); the fitted width and wing against a real peak
   (ADR 0062), then a retune after an hour of drift.
3. A dated report in `bench/reports/`.

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0065. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021; a sixth
  beside them by 0064, its past-the-end semantics by 0065), stand/activity/pulse (0022; amended additively by
  0037, 0038, 0047, 0049, 0060, 0064), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; 0048–0050,
  0062), control (0036; 0046, 0050, 0057). Registry DDL v3 (0026, 0029, 0050).
- **This session:** Probe 05 run and its doc filled; ADR 0065; `InfiniiVisionX` acquires by `:SINGle`
  (+`:AER?`, `:RSTate?`) with segmented memory and a bounded wait, emulator alike; `QDac2.load` arms
  `dc:init:cont on`, `get` queries in list mode, `release` holds the point the channel is at; the list
  restarts past its end in the protocol, the simulated source, the emulator and the simulated device;
  `MARKER_TO_ANALOG_NS`; `CAPTURE_ARM_GRACE_S` 0.5 s; the L2-4 row passes; BENCH.md and the example stand.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 433 Python tests (+5 Postgres-parametrized), 4 skipped, 38 hardware-only in `packages/`, 18
  hardware-only in `bench/`; Flight Deck 124 unit tests and 13 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/probe-05` awaits the human.

## Known broken / not yet real
- **L2-3 as one shot is unrun** (the combiner is not wired); the self-trigger interim and the marker form
  are both untested on a real droop.
- **Segment readout is 0.3–0.5 s each** over the socket after the acquisition; a thousand-shot sweep spends
  minutes reading. One transfer for all segments is the next scope slice.
- **The LF-FEM's digital I/O adapter**: nothing in software can tell when it is off (the simulator shows
  the markers); BENCH.md says to check it.
- **The marker-to-analog delay (85 ns) is recorded, not applied**; a shot capture's record starts at the
  marker.
- **A triggered axis through the combiner's DC side is still 50 ms per point** (its 20 Hz low-pass).
- **Flight Deck's Sweep widget has no `stepping` control**; a triggered sweep is posted by hand or by a node.
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
**Human:** merge the PR; decide whether to re-wire the combiner for L2-3 as one shot now or leave it for
the next bench session; name the next slice. Candidates: the Sweep widget's `stepping`; one transfer for
all segments; a second OPX pulse line (ao2 → scope ch2; two lines in one shot, their skew); an OPX-ADC
capture (a capture on the sequencer's own input, Probe 02's loopback; short windows only); how a sense
range is declared; a rest level at a sweep's end; a `tuneups`/`stand_state` table; resume and parallel
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
  to run that probe"; then at the bench: "run the probe"; the digital I/O adapter screwed on; the QDAC's trigger
  moved to the right port (ADR 0065).

## Decisions pending
- **What follows** (the candidates above); whether L2-3 as one shot is run before the next slice.
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- Step 6's Open decisions (its file): how a sense range is declared; a rest level at a sweep's end; the
  time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
