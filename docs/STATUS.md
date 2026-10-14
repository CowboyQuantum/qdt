# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/bench-report` (PR against `step-5/drivers`, which is PR #25 against `main`; the
human merges #25 first, GitHub retargets the second to `main`).
**Last session:** 2026-10-14, session 2 of Step 5, at the bench. First hardware contact: the OPX1000
passed all seven sequencer conformance tests with no driver change. The laptop could not reach it at
first: the dock's Ethernet had no DHCP lease, so the OPX subnet was routed over Wi-Fi; a manual IP on
the dock adapter fixed it (the address setup is local, never committed). The human then asked why no
bench report appeared: nothing wrote one. Built `scripts/bench_report.py` (ADR 0042): a pytest plugin
that appends a section to `bench/reports/<date>-step<N>.md` after any `-m hardware` run that executed a
test, addresses redacted. Today's report is the first in the repo. Bench:
- QDAC-II over Ethernet;
- Keithley 2400-series;
- InfiniiVision X;
- OPX1000 with LF-FEMs.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ◐ **OPX1000: 7/7 on hardware** (2026-10-14). QDAC-II, SMU and scope: pass on emulators in CI; their addresses are still placeholders in the local stand file, so untested |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending |
| bench report committed | ◐ `bench/reports/2026-10-14-step5.md` (OPX only); written automatically from now on (ADR 0042) |

## Done
- Steps 0–4b DONE. ADR 0001–0042. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, each built by `from_config` with `settings["address"]`;
  `FACTORIES` maps backend keys to them:
  - `qdevil/qdac2`: LevelSource (V) + LevelSense (I).
  - `keithley/k2400`: one terminal; legacy or 2450-style dialect from `*IDN?`.
  - `keysight/infiniivision`: WaveformSense; WORD blocks resampled to the declared grid.
  - `qm/opx1000`: WaveformSource, WaveformSense, Sequencer. **Proven on hardware** for the Sequencer
    conformance program: compile once, int input stream, positional results, final frame.
  - Shared plumbing: `drivers/scpi.py` and one emulator per SCPI driver. Each emulator rejects unknown
    commands.
- **Extras:** `[qdac]`, `[keysight]` and `[smu]` add pyvisa and pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The stand file
  is gitignored; `docs/examples/example_stand/bench.stand.example.json` shows the shape.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`, loaded by `-p bench_report` from
  `pyproject.toml` (`pythonpath = ["scripts"]`, `bench_step = "5"`). One file per day, one `## Run`
  section per run, per-backend and per-test tables, commit and dirty flag, first line of each failure.
  Written only when a `hardware` test passed or failed (not when all skipped; never in CI). Redacts
  `QDT_*_ADDRESS` values, IPv4, VISA strings and `*.stand.json` names. Five L0 tests via `pytester`.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped (single-terminal SMU), 23 hardware-only; Flight
  Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR #25 (`step-5/drivers`) awaits review; this session's PR stacks on it.

## Known broken / not yet real
- **Three drivers have not touched hardware:** QDAC-II, Keithley, InfiniiVision X. Their SCPI is from
  the manuals; the emulators encode the same reading. The local `bench.stand.json` still has placeholder
  addresses for them (the session checked: the hostnames do not resolve).
- **qm-qua deprecation:** the OPX driver's QUA config carries a `version` key that qm-qua 1.4.1 warns
  is deprecated since 1.2.2 and removed in 2.0. Drop it next time the driver is touched.
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
1. Merge PR #25, then this session's PR.
2. Put the QDAC-II, SMU and scope addresses into the local `bench.stand.json` (the OPX one is in).
   Make sure the dock Ethernet adapter still has its manual IP on the instruments' subnet. Then, from a
   session or a shell (a session reads the addresses out of the stand file):
   `uv run pytest packages/qdt-lab -m hardware -v`. The report appends itself; commit it. A session
   can fix the failures, driver and emulator together.
3. Set the scope's trigger to Auto first, or its tests hang until the VISA timeout.
4. Write `bench.stand.json`'s channels for what is actually cabled, and run
   `uv run python -m qdt_server --stand bench.stand.json --device-id <id> --ui apps/flightdeck/dist`
   for a first sweep in the browser.

**Then:** the OPX calibration constants; the L1 and L2 suites in `bench/` with their reports; and the
linear and exponential fits as curated methods.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:**
  - a chop's difference is recorded (ADR 0037);
  - additive changes without a version bump are accepted (ADR 0037);
  - the operating point comes before Step 5 (ADR 0038);
  - wall-clock CI gates are advisory (ADR 0039);
  - no surrogate DUT (ADR 0040);
  - drivers first, simple; fits later (ADR 0041);
  - bench reports must appear by themselves after a hardware run (ADR 0042).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
