# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/l1-smu` (PR against `main`; the human merges). PRs #25–#31 merged 2026-10-14.
**Last session:** 2026-10-14, session 8 of Step 5, at the bench. **L1 row 2 passes:** the SMU (a 2450,
front terminals, banana → BNC) into the scope at five levels from −1.5 V to +1.5 V, within the HD3
datasheet's DC measurement accuracy. The DC loopback test now covers both DC sources with one shared
cable: `QDT_L1_DC_SOURCES` names the cabled ones, the rest skip before any instrument opens. The SMU had
taken a new self-assigned address; mDNS (`dns-sd -B _scpi-raw._tcp`) found it in seconds, which is the
way to find Keithley and Keysight instruments on the dock wire. Bench:
- QDAC-II on a fixed 10.20.x address;
- Keithley 2450 on a self-assigned 169.254 address (mDNS);
- InfiniiVision HD304MSO on a self-assigned 169.254 address (mDNS), raw socket port;
- OPX1000 with LF-FEMs.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance on all four; L1 rows 1 and 2). L1 row 3 and L2 to come |

## Done
- Steps 0–4b DONE. ADR 0001–0043. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, all four proven on hardware for what the conformance suite
  tests: `qdevil/qdac2` (TCP or USB serial, ADR 0043), `keithley/k2400` (a 2450), `keysight/infiniivision`
  (DSOX/MSOX/HD3; LEFT reference one division in), `qm/opx1000` (Sequencer program). Shared
  `drivers/scpi.py` (`open_visa(address, baud_rate=...)`); one emulator per SCPI driver.
- **L1 rows 1 and 2 (sessions 7–8):** `bench/test_l1_loopback.py`, DC levels from the QDAC and the SMU
  into one scope input, read back through `WaveformSense`; tolerance from the HD3 datasheet (gain 1.5 %
  FS + offset 0.1 div + 1 mV + 1.5 % of offset + 0.08 % FS; FS = 8 div; ±114 mV at 0.5 V/div); source
  errors not budgeted (QDAC 20-bit; 2450 ±(0.015 % + 300 µV) on 2 V). `bench/conftest.py`: `qdac`,
  `smu` (routes the 2450 to FRONT over a socket closed before the driver opens), `scope` (connect retry),
  `closing`, `scope_front_panel`. Env: `QDT_L1_DC_SOURCES`, `QDT_L1_SCOPE_CHANNEL`, `QDT_L1_QDAC_CHANNEL`.
- **Conformance fixtures close backends** (`closing`): the 2450 accepts one socket.
- **Extras:** `[qdac]` adds pyvisa, pyvisa-py and pyserial; `[keysight]` and `[smu]` add pyvisa and
  pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The local stand
  file has working addresses for all four.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`; one file per day, a section per run ("Case"
  column = parametrize id), addresses redacted. A session reads the addresses out of the local stand
  file and exports `QDT_*_ADDRESS`.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 10
  hardware-only in `bench/`; Flight Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/l1-smu` awaits the human.

## Known broken / not yet real
- **QDAC-II outputs can come up dead** (firmware 14-1.70): setpoints applied and read back, DAC code
  right, no error, 0 V on every BNC. `*RST` fixes it. Verify one channel at the start of a bench session.
  Not a driver action: a reset zeroes every channel.
- **QDAC-II current readout** in the HIGH sense range has a common-mode error of ~0.1–0.3 mA per volt
  of output; a load check needs `SENS<n>:RANG LOW` at 0 V. Not in the driver yet (decision pending).
- **Link-local addresses move.** The 2450 and the scope self-assign 169.254 addresses that change when
  they are re-plugged; find them with `dns-sd -B _scpi-raw._tcp local.` then `dns-sd -L`/`-G v4`, and
  update the local stand file. A fixed address per instrument (as the QDAC and OPX have) would end this.
- **HD3 sockets:** the VXI-11 port refuses intermittently; the raw socket port occasionally times out the
  first connect right after a session closed (the `scope` fixture retries).
- **L1 row 3 not done:** OPX AO → scope (pulse amplitude/width oracle).
- **Serial numbers in error text:** driver errors show vendor and model only; `bench_report.py` does not
  redact `*IDN?` serials (decision pending).
- **Bench network:** the Mac's dock adapter needs aliases on the 10.20 subnet (`netmask` spelled out)
  and its 169.254 self-assigned address; its 10.20 alias has a /8 mask by accident.
- **qm-qua deprecation:** the OPX driver's QUA config carries a deprecated `version` key.
- **Today's report** holds many runs, including failed ones; the plugin never rewrites (ADR 0042).
- **OPX calibration constants** (`INTEGRATION_TO_VOLTS`, `RAW_ADC_TO_VOLTS`) are assumptions until an
  OPX AO → AI loopback at a known level.
- **QDAC-II load:** driving the 50 Ω OPX input from the QDAC (L2-1) needs the load check in BENCH.md § L2.
- **OPX results:** one frame per result at job end; maps fill line by line (one stage per stepped point).
- **OPX `drive`:** not supported on the LF-FEM stage.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human, at the bench:**
1. Merge the PR.
2. L1 row 3: cable OPX analog out 1 → a scope input. A session writes the pulse oracle (amplitude and
   width against the OPX LF-FEM output spec) and runs it; the same loopback moved to an OPX input then
   pins the OPX calibration constants.
3. The first sweep in the browser on the real stand:
   `uv run python -m qdt_server --stand bench.stand.json --device-id <id> --ui apps/flightdeck/dist`.

**Then (sessions):** L2-1 through the bias tee with the plane fit, L2-3 with the single exponential, as
curated `qdt-analysis` methods; the QDAC current-sense range on the channel declaration; close Step 5.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:** a chop's difference is recorded (0037); additive changes without a version bump are
  accepted (0037); the operating point comes before Step 5 (0038); wall-clock CI gates are advisory
  (0039); no surrogate DUT (0040); drivers first, simple; fits later (0041); bench reports write
  themselves (0042); USB serial counts for the QDAC-II (0043); drivers are recreated here rather than
  adapted from QCoDeS, an adapter only if breadth is ever needed (discussion, no ADR).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
