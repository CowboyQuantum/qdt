# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/l1-loopback` (PR against `main`; the human merges). PRs #25–#30 merged 2026-10-14.
**Last session:** 2026-10-14, session 7 of Step 5, at the bench. **First L1 loopback passes:** QDAC ch01 →
scope ch1, five levels from −1.5 V to +1.5 V, each read back as the mean of one record through the
`WaveformSense` protocol, within the HD3 datasheet's single-cursor DC measurement accuracy (±114 mV at
0.5 V/div). `bench/test_l1_loopback.py` and the bench fixtures in `bench/conftest.py` are the first real
content of `bench/`. Most of the session went to a QDAC-II fault: its analog outputs sat at 0 V while
the firmware reported every setpoint applied, after its boot history that day (software restart over
USB, power cycle without a cable, a move between switches). `*RST` brought them back; recorded as a quirk
in `docs/BENCH.md`, with the current-sense caveat that hid it. Bench:
- QDAC-II on a fixed 10.20.x address, verified on Ethernet;
- Keithley 2450 (proven session 3, unplugged since);
- InfiniiVision HD304MSO on a self-assigned 169.254 address, raw socket port (VXI-11 refuses
  intermittently);
- OPX1000 with LF-FEMs (proven session 2).

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance on all four; L1 row 1). L1 rows 2–3 and L2 to come |

## Done
- Steps 0–4b DONE. ADR 0001–0043. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, all four proven on hardware for what the conformance suite
  tests: `qdevil/qdac2` (TCP or USB serial, ADR 0043), `keithley/k2400` (a 2450), `keysight/infiniivision`
  (DSOX/MSOX/HD3; LEFT reference one division in), `qm/opx1000` (Sequencer program). Shared
  `drivers/scpi.py` (`open_visa(address, baud_rate=...)`); one emulator per SCPI driver.
- **L1 row 1 (session 7):** `bench/test_l1_loopback.py`, QDAC → scope DC levels, tolerance from the HD3
  datasheet (gain 1.5 % FS + offset 0.1 div + 1 mV + 1.5 % of offset + 0.08 % FS; FS = 8 div).
  `bench/conftest.py`: `qdac`, `scope` fixtures from `QDT_*_ADDRESS` (skip when unset), `closing`,
  `scope_front_panel` (vertical settings over a second VISA session; the protocol leaves them to the user).
  `QDT_L1_QDAC_CHANNEL` picks the cabled channel (default `ch01`).
- **Conformance fixtures close backends** (`closing`): the 2450 accepts one socket.
- **Extras:** `[qdac]` adds pyvisa, pyvisa-py and pyserial; `[keysight]` and `[smu]` add pyvisa and
  pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The local stand
  file has working addresses for all four (scope in socket form).
- **Bench reports (ADR 0042):** `scripts/bench_report.py`; one file per day, a section per run, addresses
  redacted. A session reads the addresses out of the local stand file and exports `QDT_*_ADDRESS`.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped (single-terminal SMU), 23 hardware-only in
  `packages/`, 5 hardware-only in `bench/`; Flight Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/l1-loopback` awaits the human.

## Known broken / not yet real
- **QDAC-II outputs can come up dead** (firmware 14-1.70): setpoints applied and read back, DAC code
  right, no error, 0 V on every BNC. `*RST` fixes it. Verify one channel at the start of a bench session.
  Root cause unknown; the boot history that day (restart over USB, power cycle without a cable) is the
  suspect. Not a driver action: a reset zeroes every channel.
- **QDAC-II current readout** in the HIGH sense range has a common-mode error of ~0.1–0.3 mA per volt
  of output; it hides a 1 MΩ load. A load check needs `SENS<n>:RANG LOW` at 0 V. Not in the driver yet
  (`integration_s` sets the aperture only). Candidate: declare the sense range on the `ChannelMap`, or
  pick it from the quantity's expected magnitude (ADR-level).
- **HD3 VXI-11** (`::INSTR`) refuses connections intermittently; the socket form is reliable. The driver
  does not care; the stand file and the bench use `::5025::SOCKET`.
- **L1 rows 2 and 3 not done:** SMU → scope ch 2 (SMU unplugged), OPX AO → scope ch 3 (pulse oracle).
- **Serial numbers in error text:** driver errors show vendor and model only; `bench_report.py` does not
  redact `*IDN?` serials (decision pending).
- **Bench network:** the Mac's dock adapter needs aliases on the 10.20 subnet (`netmask` spelled out)
  and its 169.254 self-assigned address; its 10.20 alias has a /8 mask by accident.
- **qm-qua deprecation:** the OPX driver's QUA config carries a deprecated `version` key.
- **Today's report** holds many runs, including failed ones against stale addresses, an open loop and the
  dead QDAC; the plugin never rewrites, pruning is the human's call (ADR 0042).
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
2. L1 row 3: cable OPX analog out 1 → scope ch 3 (keep QDAC ch01 → scope ch1). A session writes the
   pulse-amplitude/width oracle against the OPX LF-FEM output spec and runs it; the same loopback, moved
   to an OPX input, then pins the OPX calibration constants.
3. L1 row 2 when the SMU is back: SMU → scope ch 2.
4. The first sweep in the browser on the real stand:
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
