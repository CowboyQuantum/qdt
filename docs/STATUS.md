# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/drivers` (PR against `main`).
**Last session:** 2026-10-14. The human cut the surrogate DUT (ADR 0040) and asked for the drivers
directly, kept simple. Linear and exponential fits come later. Bench:
- QDAC-II over Ethernet;
- Keithley 2400-series;
- InfiniiVision X;
- OPX1000 with LF-FEMs.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ◐ passes on each driver's emulator in CI; the OPX's QUA and config are validated offline by qm-qua. **The first bench run is the next action** |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators (`test_a_sweep_runs_on_the_real_drivers_streams_and_records`); hardware run pending |
| bench report committed | ✘ |

## Done
- Steps 0–4b DONE. ADR 0001–0041. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, each built by `from_config` with `settings["address"]`;
  `FACTORIES` maps backend keys to them:
  - `qdevil/qdac2`: LevelSource (V) + LevelSense (I).
  - `keithley/k2400`: one terminal; legacy or 2450-style dialect from `*IDN?`.
  - `keysight/infiniivision`: WaveformSense; WORD blocks resampled to the declared grid.
  - `qm/opx1000`: WaveformSource, WaveformSense, Sequencer.
    - Compile once, then an int input stream (Probe 01).
    - Sticky levels; `Affine` and `difference`.
    - `QuaEmitter` packages stages for it.
  - Shared plumbing: `drivers/scpi.py` and one emulator per SCPI driver. Each emulator rejects unknown
    commands.
- **Extras:** `[qdac]`, `[keysight]` and `[smu]` add pyvisa and pyvisa-py; `[opx]` adds qm-qua 1.4.1. No
  pin conflicts.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The stand file
  is gitignored; `docs/examples/bench.stand.example.json` shows the shape.
- 311 Python tests (+5 Postgres-parametrized), 4 skipped (single-terminal SMU), 23 hardware-only; Flight
  Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. The PR for `step-5/drivers` awaits review.

## Known broken / not yet real
- **No driver has touched hardware.** Every SCPI command is from the manuals and listed in each driver's
  docstring. The emulators encode the same reading, so the first `-m hardware` run is the real check.
- **OPX calibration constants** (`INTEGRATION_TO_VOLTS`, `RAW_ADC_TO_VOLTS`) are assumptions until an
  OPX AO → AI loopback at a known level.
- **QDAC-II load:** driving the 50 Ω OPX input from the QDAC (L2-1) needs the load check in BENCH.md § L2.
- **OPX results:** a stage's results arrive when its job ends (one frame per result). Maps still fill
  line by line, because the executor runs one stage per stepped point.
- **OPX `drive`:** not supported on the LF-FEM stage.
- Carried over:
  - the diamond estimator needs a cold sensor (ADR 0030);
  - zero-clipping in the dot model (ADR 0020);
  - overlays drawn in one colour;
  - the Postgres suite runs only in CI (no docker here);
  - `FINISH_LINE.md` TODO (human);
  - on Windows, run pnpm as `corepack pnpm`.

## Next action
**Human, at the bench:**
1. Export `QDT_QDAC2_ADDRESS`, `QDT_SMU_ADDRESS`, `QDT_SCOPE_ADDRESS` and `QDT_OPX_ADDRESS`, then run
   `uv run pytest packages/qdt-lab -m hardware -v`. A session can fix the failures, driver and emulator
   together.
2. Write a local `bench.stand.json` from the example, and run
   `uv run python -m qdt_server --stand bench.stand.json --device-id <id> --ui apps/flightdeck/dist`
   for a first sweep in the browser.

**Then:** the OPX calibration constants; the L1 and L2 suites in `bench/` with the dated report; and
the linear and exponential fits as curated methods.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:**
  - a chop's difference is recorded (ADR 0037);
  - additive changes without a version bump are accepted (ADR 0037);
  - the operating point comes before Step 5 (ADR 0038);
  - wall-clock CI gates are advisory (ADR 0039);
  - no surrogate DUT (ADR 0040);
  - drivers first, simple; fits later (ADR 0041).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
