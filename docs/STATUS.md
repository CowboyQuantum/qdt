# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** none in progress. **Step 6b — Flight Deck workspace is DONE** (opened 2026-10-15, closed
2026-10-16 after six sessions, ADR 0054–0059). Step 6 is DONE (its L3 confirmation is the first fridge task,
below). **Step 7 waits for manager sign-off** (plan Open Decision #5); what comes next is the human's call.
**Branch:** `step-6b/script-close` (PR against `main`; the human merges). PRs #25–#56 merged 2026-10-14/16.
**Last session:** 2026-10-16, Step 6b session 6 (not at the bench). **The Script widget placeholder; the step
closes** (ADR 0059). An editor (per browser) beside the allowed API as data (`sweep`, `levels`, `run`, `wait`,
`analyze`, `device`), a stage button that lints (allow-list, a `qdt.x` without a call, brackets and quotes as a
stack across lines, comments and strings ignored) and reports that nothing ran. No execution path; a sandbox is
its own ADR. With it every Step 6b deliverable is done and every exit criterion met (table below); the step file
and `docs/steps/README.md` say DONE.

## Step 6b close-out
| Exit criterion | State |
|---|---|
| `panel.ts` is gone; every former panel capability exists as a widget; all e2e green | ✔ (ADR 0058) |
| Two plot panes show live and a stored record simultaneously with independent cuts | ✔ (ADR 0055; e2e) |
| Exactly one Run control, bound to a compiled plan with a visible identity and stale marker | ✔ (ADR 0056) |
| Layout persists and restores; `+` refuses below the min pane height | ✔ (ADR 0054; e2e) |

Deliverables 1–6: shell (0054), plot panes + History (0055), Sweep + Pulse + one Run (0056), Levels + Virtual
gates with `GET /levels/state` (0057), Analysis + Tune-up with the panel deleted (0058), Script placeholder
(0059). Widgets: `plot`, `sweep`, `pulse`, `levels`, `gates`, `history`, `analysis`, `tuneup`, `script`, `empty`.
Open decisions carried, not closed: layout as a schema object; the script sandbox (the allow-list should come
from it); the release mirror's first widgets; themes in the registry.

## Fridge (L3) tasks — not a gate; run when a fridge exists
1. Run the three-node tune-up (sensor-operating-point → charge-lattice → virtual-lattice) on a real device through
   `POST /tuneups`; compare outcomes to the sim's (`SimResult` fixtures). Confirmation, not discovery: a surprise
   is a bug in a sim scenario or a node, filed as such.
2. The diamond estimator on a cold sensor (ADR 0030); `flank_offset_v` against a real peak (ADR 0052).
3. A dated report in `bench/reports/` (the ladder has no fridge report format yet; write one with the first run).

## Done
- **Steps 0–6 and 6b DONE.** ADR 0001–0059. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038, 0047, 0049), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033; Step 6 objects beside it by 0048–0050), control (0036; amended additively by 0046,
  0050; `ChannelLevel` beside it by 0057). Registry DDL v3 (0026, 0029, 0050).
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `qdt-telemetry`, `apps/flightdeck`.
- 395 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 119 unit tests and 9 e2e.

## In flight
- Nothing uncommitted. PR for `step-6b/script-close` awaits the human.

## Known broken / not yet real
- **The Script widget runs nothing**: stage lints and says so; the allow-list is hand-written until a sandbox ADR
  generates it.
- **Flight Deck carry-overs (Step 6b):** an analysis names its record from History or the picker, not from a
  plot pane yet; two widgets refresh records after a run (no server push); the simulator's live device and a
  run's device diverge (ADR 0057); a simulated gate reads back null; the Levels widget polls every 2 s; limits
  are a browser setting; the coupling matrix is per browser; a stage sweep needs the Pulse widget mounted; one
  run at a time from the UI; Run compiles again when stale (0056); no colormap in the ⚙ menu; per-pane view state
  does not survive a reload (0055); no Google Fonts link; the strip's stand/device read "?" without a server.
- **`provenance_check.sh` matches bare substrings**; a word-boundary pattern is a one-line fix.
- Step 6 carry-overs: the held operating point is server memory (a `stand_state` table later); click-to-set only
  for axes named after stand DC channels; `flank_offset_v` is a judgment (0052); the diamonds method needs a cold
  sensor (0030); `TuneUp` not persisted, one at a time, no resume/parallel (0050); the bench has one OPX pulse
  line and no `SG`/`bias`/`sensor`; `detect_transitions` reports `ok` on a constant map; `SimScenario.model`
  overrides scalars only; QDAC-II quirks (BENCH.md); nothing in a sweep plays a waveform; captures sequential;
  the trace view has no axes/labels/output curve; the exponential's edge detector is a heuristic (0046); the
  plane fit is OLS (0045); OPX input offset not applied; `bench_report.py` does not redact serials; qm-qua
  deprecations; zero-clipping in the dot model (0020); Postgres suite only in CI; `FINISH_LINE.md` TODO (human);
  Windows pnpm via `corepack pnpm`.

## Next action
**Human:**
1. Merge the PR. Step 6b is closed; look at the whole workspace once in `pnpm dev` against `python -m qdt_server`.
2. **Name what comes next.** Step 7 (other sources onto the substrate: `qdt-telemetry` ingest, the internal
   extension, lab PC deployment) is gated by manager sign-off. Without it, the candidates are:
   - a Step 6 Open decision with an ADR and a slice: `PlayedWaveform` (a waveform played inside a sweep, ADR
     0047's other half), sub-ms stepping (Probe 04's consequence), how a sense range is declared;
   - a `sensor_peak` method retiring `flank_offset_v` (ADR 0052);
   - a bench session: a second OPX pulse line for the stability nodes, the QDevil report;
   - Flight Deck follow-ups from the list above (a colormap choice, per-pane view state, "analyse the record in
     Plot N", the tune-up's `virtual_gates` into the coupling matrix, a `records:changed` push).
3. Step 6's Open decisions (its file) and the QDevil report still wait.

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
  the Step 6b spec arrives as a chat patch (ADR 0054); "let's put off L3 and close step 6": Step 6 closes on the
  simulator, the L3 confirmation is the first fridge task; "go with 6b": Step 6b opens, ADR 0054 is accepted,
  the shell is session 1.
- **2026-10-16:** PRs #52–#56 merged without a word, so sessions 2–6 (ADR 0055–0059) followed the step file's
  order, taking STATUS's stated defaults where a decision was pending; "the flight deck ci didn't pass": two
  timing failures fixed in #56 (the Levels table keeps its rows across polls; e2e scenarios declare 180 s).

## Decisions pending
- **What follows Step 6b** (the list above).
- Deliverable 4's defaults, taken: readback null (not omitted); the limit a browser setting. Say if either changes.
- Step 6b's Open decisions (its file): layout as a schema object; the script sandbox; the release mirror's
  first widgets; themes per browser or in the registry.
- Flight Deck follow-ups: a Google Fonts link; a colormap choice; queueing a second run; the tune-up's
  `virtual_gates` into the coupling matrix; "analyse the record in Plot N"; per-pane view state across a reload.
- Step 6's Open decisions (its file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table and a `stand_state` table; resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump); a `sensor_peak` method.
- `bench_report.py` and `*IDN?` serials; the dot model's zero-clipping; the diamond estimator on warm edges.
