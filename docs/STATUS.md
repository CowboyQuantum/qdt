# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/bench-qdac` (PR against `main`; the human merges). PRs #25, #26, #27 merged
2026-10-14.
**Last session:** 2026-10-14, session 4 of Step 5, at the bench. Third instrument proven: the QDAC-II
passes its three LevelSource conformance tests over the rear USB port. Getting there: the instrument is
DHCP-only, sat on a wire with no DHCP server holding a stale lease, and has no link-local fallback (a
sweep of all of 169.254/16 found nothing). Over USB serial it got a fixed LAN address (stored, confirmed by
readback), but the Ethernet cable was moved before it was seen on the wire. The transport gained a baud
rate and pyserial joined the `[qdac]` extra so a serial VISA address works everywhere an address does
(ADR 0043). Bench:
- QDAC-II, today over USB (its LAN address set, unverified);
- Keithley 2400-series (a 2450; proven session 3, now unplugged);
- InfiniiVision X (not yet reached);
- OPX1000 with LF-FEMs (proven session 2).

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ◐ **OPX1000 7/7**, **Keithley 2450 5/5 (+2 single-terminal skips)**, **QDAC-II 3/3 (USB)** on hardware, 2026-10-14. Scope: address still a placeholder in the local stand file |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending |
| bench report committed | ◐ `bench/reports/2026-10-14-step5.md` (OPX, SMU, QDAC runs); written automatically (ADR 0042) |

## Done
- Steps 0–4b DONE. ADR 0001–0043. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, each built by `from_config` with `settings["address"]`;
  `FACTORIES` maps backend keys to them:
  - `qdevil/qdac2`: LevelSource (V) + LevelSense (I). **Proven on hardware (USB):** set, readback,
    independent channels. A serial address defaults to 921600 baud (ADR 0043). Current sensing is not in
    the suite yet (no QDAC loopback pair registered).
  - `keithley/k2400`: one terminal; legacy or 2450-style dialect from `*IDN?`. **Proven on a 2450.**
  - `keysight/infiniivision`: WaveformSense; WORD blocks resampled to the declared grid. Not yet reached.
  - `qm/opx1000`: WaveformSource, WaveformSense, Sequencer. **Proven on hardware** for the Sequencer
    conformance program.
  - Shared plumbing: `drivers/scpi.py` (`open_visa(address, baud_rate=...)`) and one emulator per SCPI
    driver. Each emulator rejects unknown commands.
- **Conformance fixtures close backends** (`closing` fixture, session 3): the 2450 accepts one socket.
- **Extras:** `[qdac]` adds pyvisa, pyvisa-py and pyserial; `[keysight]` and `[smu]` add pyvisa and
  pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The stand file
  is gitignored; `docs/examples/example_stand/bench.stand.example.json` shows the shape.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`. One file per day, one `## Run` section per
  run, addresses redacted. A session runs hardware tests by reading the address out of the local stand
  file and exporting `QDT_*_ADDRESS` in the same command.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped (single-terminal SMU), 23 hardware-only; Flight
  Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/bench-qdac` awaits the human.

## Known broken / not yet real
- **QDAC-II on Ethernet unverified.** Its LAN is set to a fixed address on the OPX's subnet (DHCP off,
  /24, stored). It was never seen on the wire: after `SYSTem:REStart` nothing answered, then the cable
  was moved. Next time: cable in, power cycle, `ping` it, put `TCPIP::<ip>::5025::SOCKET` in the stand
  file. The procedure for setting the address is in `docs/BENCH.md`. The local stand file currently
  carries the USB address `ASRL/dev/cu.usbserial-NNNN::INSTR`, which works for the server too.
- **Scope untested:** its address is still a placeholder in the local stand file. Set its trigger to
  Auto before the run, or the digitize hangs until the VISA timeout.
- **Bench network:** instruments on the dock wire self-assign 169.254 addresses (the 2450 did) or carry a
  fixed 10.20.x address (the OPX, now the QDAC). The Mac's dock adapter needs an alias on each subnet,
  with `netmask` spelled out (`ifconfig en11 alias <ip> netmask 255.255.255.0`); its current alias has
  a /8 mask by accident, and it lost its 169.254 self-assigned address when the manual one was set, so
  169.254 traffic now routes over Wi-Fi.
- **qm-qua deprecation:** the OPX driver's QUA config carries a `version` key that qm-qua 1.4.1 warns
  is deprecated and removed in 2.0. Drop it next time the driver is touched.
- **Today's report** holds runs against stale addresses and single-test diagnostic runs; the plugin
  never rewrites, pruning is the human's call (ADR 0042).
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
2. Scope: put its address in the local `bench.stand.json`, set the trigger to Auto, and ask a session
   to run `-m hardware -k infiniivision`. That completes the four-instrument conformance row.
3. QDAC-II on Ethernet: cable in, power cycle, ask a session to ping it and switch the stand file to the
   TCP address.
4. Then the first sweep in the browser:
   `uv run python -m qdt_server --stand bench.stand.json --device-id <id> --ui apps/flightdeck/dist`.

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
  - bench reports must appear by themselves after a hardware run (ADR 0042);
  - instruments are brought up one at a time as they get addresses; USB serial counts for the QDAC-II
    when the wire is not there (ADR 0043).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
