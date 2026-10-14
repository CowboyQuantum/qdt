# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/bench-smu` (PR against `main`; the human merges). PRs #25 (drivers) and #26 (bench
reports, ADR 0042) merged 2026-10-14.
**Last session:** 2026-10-14, session 3 of Step 5, at the bench. Second instrument proven: the Keithley
(a 2450) passes the conformance suite. One failure on the first run, fixed in the harness: the 2450
accepts a single raw-socket connection and resets any second one, and the suite's fixtures never closed a
backend, so the fourth test's connection was refused. Fixtures now close every backend at teardown
(`closing` in `packages/qdt-lab/tests/conftest.py`); the driver docstring records the limit. The QDAC-II
could not be found: it is on a wire with no DHCP server (the dock, now through a Fortinet switch), the
manual documents no link-local fallback, and a sweep of all of 169.254/16 found its MAC nowhere. It needs
a fixed address set over USB serial, or a DHCP server on its wire. Bench:
- QDAC-II over Ethernet;
- Keithley 2400-series (a 2450 on the bench);
- InfiniiVision X;
- OPX1000 with LF-FEMs.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ◐ **OPX1000 7/7** and **Keithley 2450 5/5 (+2 single-terminal skips)** on hardware, 2026-10-14. QDAC-II: no address yet. Scope: address still a placeholder in the local stand file |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending |
| bench report committed | ◐ `bench/reports/2026-10-14-step5.md`, six run sections (OPX, then the SMU's failure, diagnosis and pass); written automatically (ADR 0042) |

## Done
- Steps 0–4b DONE. ADR 0001–0042. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, each built by `from_config` with `settings["address"]`;
  `FACTORIES` maps backend keys to them:
  - `qdevil/qdac2`: LevelSource (V) + LevelSense (I). Not yet reached.
  - `keithley/k2400`: one terminal; legacy or 2450-style dialect from `*IDN?`. **Proven on a 2450:**
    source, readback, sense follows source within 1 mV, NPLC from `integration_s`.
  - `keysight/infiniivision`: WaveformSense; WORD blocks resampled to the declared grid. Not yet reached.
  - `qm/opx1000`: WaveformSource, WaveformSense, Sequencer. **Proven on hardware** for the Sequencer
    conformance program.
  - Shared plumbing: `drivers/scpi.py` and one emulator per SCPI driver. Each emulator rejects unknown
    commands.
- **Conformance fixtures close backends** (`closing` fixture): `level_source`, `level_loopback_factory`,
  `waveform_sense`, `sequencer_and_program` register what they build; teardown calls `close()` where it
  exists, last first, once per object.
- **Extras:** `[qdac]`, `[keysight]` and `[smu]` add pyvisa and pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The stand file
  is gitignored; `docs/examples/example_stand/bench.stand.example.json` shows the shape.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`, loaded by `-p bench_report` from
  `pyproject.toml`. One file per day, one `## Run` section per run, addresses redacted. A session runs
  hardware tests by reading the address out of the local stand file and exporting `QDT_*_ADDRESS` in the
  same command.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped (single-terminal SMU), 23 hardware-only; Flight
  Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/bench-smu` awaits the human.

## Known broken / not yet real
- **QDAC-II has no IP address.** It is DHCP-only from the factory (manual v2.4) and sits on a wire with no
  DHCP server. Options: USB serial (`screen /dev/cu.usbserial-NNNN 921600`, then
  `syst:comm:lan:dhcp off`, `:ipad`, `:smask`, `:gat`, `:upd`, `syst:rest`), or Internet Sharing on the
  Mac so it hands out a lease (then the lease is in `/var/db/dhcpd_leases`). The human is finding a USB
  cable.
- **Scope untested:** its address is still a placeholder in the local stand file. Set its trigger to
  Auto before the run, or the digitize hangs until the VISA timeout.
- **Bench network:** instruments on the dock wire self-assign 169.254 addresses (the 2450 did) or carry a
  fixed 10.20.x address (the OPX). The Mac's dock adapter needs an alias on each fixed subnet, with
  `netmask` spelled out (`ifconfig en11 alias <ip> netmask 255.255.255.0`); the current alias has a /8
  mask by accident, which also captures 10.x traffic that used to go over Wi-Fi.
- **qm-qua deprecation:** the OPX driver's QUA config carries a `version` key that qm-qua 1.4.1 warns
  is deprecated and removed in 2.0. Drop it next time the driver is touched.
- **Today's report** holds one run against a stale SMU address (17:53 UTC, all connection errors) and two
  single-test diagnostic runs; the plugin never rewrites, pruning is the human's call (ADR 0042).
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
   to run `-m hardware -k infiniivision`.
3. QDAC-II: give it an address over USB serial (commands above) or turn on Internet Sharing to the dock
   adapter and power-cycle it with the cable in; then put the address in the stand file and ask a
   session to run `-m hardware -k qdac2`.
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
  - instruments are brought up one at a time as they get addresses; the QDAC waits for a USB cable.

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
