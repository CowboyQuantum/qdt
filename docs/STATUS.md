# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/bench-scope` (PR against `main`; the human merges). PRs #25–#28 merged 2026-10-14.
**Last session:** 2026-10-14, session 5 of Step 5, at the bench. Fourth instrument proven: the scope,
an HD304MSO (InfiniiVision HD3 series), passes all six WaveformSense conformance tests. Two driver
fixes, each mirrored in the emulator: the model check admits `HD3…` beside `DSOX`/`MSOX`, and the LEFT
timebase reference sits one graticule division (10 % of the range) in from the screen's left edge, so the
driver places the reference at `start + range/10` and the capture starts at `start`. Driver errors no
longer echo the full `*IDN?` string (it carries the serial number; rule 7). **All four instruments now
pass the conformance suite on hardware.** Bench:
- QDAC-II, over USB (LAN address set, unverified on Ethernet);
- Keithley 2450 (proven session 3, unplugged since);
- InfiniiVision HD304MSO on a self-assigned 169.254 address;
- OPX1000 with LF-FEMs (proven session 2).

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ **OPX1000 7/7, Keithley 2450 5/5 (+2 single-terminal skips), QDAC-II 3/3 (USB), HD304MSO 6/6**, all 2026-10-14. The suite has no QDAC current-sense loopback and no real `WaveformSource` yet |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (all four instruments; written automatically, ADR 0042). L1/L2 reports still to come |

## Done
- Steps 0–4b DONE. ADR 0001–0043. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, each built by `from_config` with `settings["address"]`;
  `FACTORIES` maps backend keys to them. All four proven on hardware for what the suite tests:
  - `qdevil/qdac2`: LevelSource (V) + LevelSense (I). Set, readback, independent channels over USB; a
    serial address defaults to 921600 baud (ADR 0043). Current sensing untested (no loopback pair).
  - `keithley/k2400`: one terminal; legacy or 2450-style dialect from `*IDN?`. Source, readback, sense
    follows source, NPLC from `integration_s`, on a 2450.
  - `keysight/infiniivision`: WaveformSense on DSOX/MSOX/HD3; records land whole on the declared grid,
    final frame, rejections. LEFT reference = one division in (`LEFT_REFERENCE_FRACTION`).
  - `qm/opx1000`: WaveformSource, WaveformSense, Sequencer. Sequencer conformance program on hardware.
  - Shared plumbing: `drivers/scpi.py` (`open_visa(address, baud_rate=...)`) and one emulator per SCPI
    driver; each rejects unknown commands and encodes the bench's reading of the instrument.
- **Conformance fixtures close backends** (`closing` fixture): the 2450 accepts one socket.
- **Extras:** `[qdac]` adds pyvisa, pyvisa-py and pyserial; `[keysight]` and `[smu]` add pyvisa and
  pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The stand file
  is gitignored; `docs/examples/example_stand/bench.stand.example.json` shows the shape. The local one
  now has real addresses for all four.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`. One file per day, one `## Run` section per
  run, addresses redacted. A session runs hardware tests by reading the address out of the local stand
  file and exporting `QDT_*_ADDRESS` in the same command.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped (single-terminal SMU), 23 hardware-only; Flight
  Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/bench-scope` awaits the human.

## Known broken / not yet real
- **QDAC-II on Ethernet unverified.** Its LAN is set to a fixed address on the OPX's subnet (DHCP off,
  /24, stored). Never seen on the wire yet. Next: cable in, power cycle, `ping`, then
  `TCPIP::<ip>::5025::SOCKET` in the stand file. Procedure in `docs/BENCH.md`.
- **Serial numbers in error text:** driver `ValueError`s now show vendor and model only. The bench
  report plugin does not redact serials; one leaked into an uncommitted report section today and was
  scrubbed by hand before commit. Consider redacting the third `*IDN?` field in `scripts/bench_report.py`.
- **Bench network:** the 2450 and the scope self-assign 169.254 addresses; the OPX and now the QDAC carry
  fixed 10.20.x addresses. The Mac's dock adapter needs an alias on each subnet, `netmask` spelled out
  (`ifconfig en11 alias <ip> netmask 255.255.255.0`); its 10.20 alias has a /8 mask by accident.
- **qm-qua deprecation:** the OPX driver's QUA config carries a `version` key that qm-qua 1.4.1 warns
  is deprecated and removed in 2.0. Drop it next time the driver is touched.
- **Today's report** holds runs against stale addresses and diagnostic runs; the plugin never rewrites,
  pruning is the human's call (ADR 0042).
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
1. Merge the PR.
2. Cable the L1 loopbacks from `docs/BENCH.md` (QDAC → scope ch 1, SMU → scope ch 2, OPX AO → scope
   ch 3) and get the QDAC back on Ethernet (cable in, power cycle; a session pings it and switches the
   stand file to the TCP address).
3. The first sweep in the browser on the real stand:
   `uv run python -m qdt_server --stand bench.stand.json --device-id <id> --ui apps/flightdeck/dist`.

**Then (sessions):** the L1 loopback suite in `bench/` with numeric oracles and its report; the OPX
calibration constants from the OPX AO → AI loopback; L2-1 with the plane fit and L2-3 with the single
exponential as curated `qdt-analysis` methods; close Step 5.

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
  - bench reports must appear by themselves after a hardware run (ADR 0042);
  - instruments are brought up one at a time as they get addresses; USB serial counts for the QDAC-II
    when the wire is not there (ADR 0043).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
