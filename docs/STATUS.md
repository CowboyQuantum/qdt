# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6 — Closed-loop tuning → `docs/steps/06-closed-loop-tuning.md` (IN PROGRESS, opened
2026-10-15). **Step 5 is DONE** (ADR 0040–0047; every exit criterion met, every ladder row run on hardware).
**Branch:** `step-6/open` (PR against `main`; the human merges). PRs #25–#41 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 1 (not at the bench): closed Step 5 (its file, the steps index)
and opened Step 6's file with the decisions Step 5 left behind, each with its bench evidence. Nothing of
Step 6 is built yet. Bench, as left on 2026-10-15:
- QDAC-II (USB serial), ch01 → combiner DC in, **ch02 dead**, ch03 → scope ch2; both at 0 V;
- OPX1000 LF-FEM ao1 → combiner pulse in; the board's output → scope ch1 at 1 MΩ (the L2 wiring, intact);
- Keithley 2450 on the switch, output off, no cable to the scope;
- the dock adapter needs `sudo ifconfig en11 alias 10.20.150.250 netmask 255.255.255.0` after a reboot.

## Step 6 exit criteria (from the step file)
| Criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | not started |
| first L3 contact as confirmation, not discovery | not started (L3 is never an exit criterion of a step; here it confirms) |

## Done
- **Steps 0–5 DONE.** ADR 0001–0047. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038, 0047), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036; amended additively by 0046).
- **Step 5 in one line:** four real drivers behind the frozen protocols, 18 + 5 + 3 + 6 conformance rows on
  hardware; the control path runs stage sweeps and capture sweeps on the real stand; L1 (3 rows) and L2
  (L2-1, L2-2, L2-3) pass; two curated fits proven on hardware records; Probes 02–04; bench reports.
- **Packages:** `qdt-schemas`, `qdt-lab` (protocols, simulated backends, four drivers with emulators,
  stream, experiment compiler/executor), `qdt-sim` (`SimulatedDevice`), `qdt-registry`, `qdt-analysis`
  (four curated methods), `qdt-server` (the control path), `apps/flightdeck`.
- 353 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 71 unit tests and 5 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/open` awaits the human.

## Known broken / not yet real
- **QDAC-II (firmware 14-1.70), for QDevil:** the output filter setting changes nothing (Probe 04); the LOW
  current-sense range reads ≈ 2 nA for any current; ch02 is dead (`*RST` no cure). Power-cycle the unit
  and re-check ch02; the driver never sets filter or range. Its output impedance is 50 Ω.
- **The 2450 autoranges its current measurement to 10 nA at 0 V** and then charges a cable at 10 nA; L2-2
  holds the range over the transport. A declared sense range is a Step 6 open decision.
- **Nothing in a sweep plays a waveform; a sweep leaves its last level; captures are sequential, one
  channel each; a 3-D capture variable has no Flight Deck view; Flight Deck offers every method on every
  record; the trace view has no axes, labels or output curve** — all Step 6 open decisions or deliverables
  (step file).
- **The exponential's edge detector is a heuristic** (ADR 0046); **the plane fit is ordinary least
  squares** (ADR 0045). **OPX input offset** −1.7 mV not applied; **OPX `drive`** unsupported on the LF-FEM
  stage; one frame per OPX result at job end.
- **Bench quirks** (BENCH.md): QDAC outputs can come up dead after a power cycle (`*RST` fixes that case);
  link-local addresses move; the scope answers TCP not ping, refuses a socket briefly after one closes,
  has slow SCPI (query 4.5 ms, write + `*OPC?` 44 ms), and a waiting single-shot blocks `*OPC?`.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecations:** the QUA config's `version` key; `job.halt` for `job.cancel`.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human:**
1. Merge the PR.
2. Read Step 6's Open decisions and say which come first. The step file's suggested first task is the
   schema slice's shape (`SimScenario`, `SimResult`, `CalibrationNode`) and one node against
   `SimulatedDevice`; the bench-facing decisions (`PlayedWaveform`, sub-ms stepping, sense range, rest
   level) can wait until a node needs them.
3. Report the QDAC-II findings to QDevil; power-cycle the unit when the bench allows.

**Then (sessions):** ADR for the modeling slice's Step 6 objects (what a scenario, a result and a node
are, how a node's decision is recorded); the first node (a charge-transition lattice from the stability
diagram, ADR 0029's "virtual gates, Step 6") against the sim with a committed scenario outcome; the DAG
runner; Flight Deck's DAG state display and click-to-set.

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
- **2026-10-15:** the scope is L2-1's sink; waveform capture is a server feature (ADR 0047); how fast the
  QDAC can be stepped matters for untriggered sweeps (Probe 04); finish the OPX conformance rows and L2-2
  before closing Step 5; the combiner wiring stays intact; **Step 5 closes and Step 6 opens.**

## Decisions pending
Step 6's Open decisions (step file), in the human's order. Plus: whether `bench_report.py` should redact
`*IDN?` serial fields; a default operating point per device; the dot model's zero-clipping; whether the
diamond estimator should survive warm edges.
