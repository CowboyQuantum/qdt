# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/opx-calibration` (PR against `main`; the human merges). PRs #25–#33 merged 2026-10-14.
**Last session:** 2026-10-14, session 10 of Step 5, at the bench. **Probe 02 measured the OPX input
constants** (ADR 0044) on an LF-FEM ao1 → ai1 loopback against the scope-verified pulse: the input reads
inverted at 1.155 × the assumed 2⁻¹² scale on both the raw-ADC and the integration path (they agree to
0.5 %, linear to < 0.3 mV over ±0.25 V), and the time of flight is 180 ns, not 24 (QOP 3.7 rejects < 28;
the driver's old value would have failed). The driver carries the measured values with provenance.
Bench: QDAC-II (fixed 10.20.x), Keithley 2450 and HD304MSO (self-assigned 169.254, mDNS), OPX1000
(fixed 10.20.x). The cable is on OPX ao1 → ai1.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the path runs in CI through the server on real drivers over emulators; hardware run pending. The OPX input is now calibrated, so its measures mean volts |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance on all four; L1 rows 1–3); Probe 02 findings in its doc and fixtures. L2 to come |

## Done
- Steps 0–4b DONE. ADR 0001–0044. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** in `qdt_lab.drivers`, all four proven on hardware: `qdevil/qdac2` (TCP or USB
  serial, ADR 0043), `keithley/k2400` (a 2450), `keysight/infiniivision` (DSOX/MSOX/HD3; LEFT reference
  one division in), `qm/opx1000` (Sequencer program, `WaveformSource.play`; input constants measured,
  ADR 0044). Shared `drivers/scpi.py`; one emulator per SCPI driver.
- **L1 complete (sessions 7–9):** `bench/test_l1_loopback.py` (QDAC and SMU DC levels, OPX pulse into
  the scope; datasheet tolerances); `bench/conftest.py` fixtures; `QDT_L1_SOURCES` names cabled sources.
- **Probe 02 (session 10):** `bench/probes/probe02/opx_calibration.py --host --fem --tof --out`; one QUA
  program plays a pulse on ao1 and reads ai1 raw and integrated at five amplitudes; fixtures
  `bench/fixtures/probe02/` (two runs). Doc `docs/probes/02-opx-input-calibration.md`.
- **Conformance fixtures close backends** (`closing`): the 2450 accepts one socket.
- **Extras:** `[qdac]` adds pyvisa, pyvisa-py and pyserial; `[keysight]` and `[smu]` add pyvisa and
  pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- **`qdt-server --stand <file>.stand.json --device-id <id>`** runs on real instruments. The local stand
  file has working addresses for all four.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`; one file per day, a section per run.
- 316 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 11
  hardware-only in `bench/`; Flight Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/opx-calibration` awaits the human.

## Known broken / not yet real
- **No hardware `WaveformSense` row for the OPX input in the conformance suite:** the suite's grid oracle
  needs a signal on the input, which is a bench loopback. Probe 02 covers the scale; the record-on-grid
  behaviour of `Opx1000.arm` on hardware is still only inferred (ADR 0044).
- **OPX input offset** −1.7 mV at 0 V in, not applied in the config.
- **QDAC-II outputs can come up dead** (firmware 14-1.70): `*RST` fixes it; verify one channel at the
  start of a bench session. Not a driver action.
- **QDAC-II current readout** in the HIGH sense range hides a 1 MΩ load; a load check needs
  `SENS<n>:RANG LOW` at 0 V. Not in the driver yet (decision pending).
- **Link-local addresses move** (2450, scope); `dns-sd -B _scpi-raw._tcp local.` finds them.
- **HD3 sockets:** VXI-11 refuses intermittently; the socket form occasionally times out the first
  connect (the `scope` fixture retries).
- **Serial numbers:** driver errors show vendor and model only; `bench_report.py` does not redact
  `*IDN?` serials (decision pending).
- **Bench network:** the Mac's dock adapter needs aliases on the 10.20 subnet (`netmask` spelled out)
  and its 169.254 self-assigned address; its 10.20 alias has a /8 mask by accident.
- **qm-qua deprecation:** the OPX driver's QUA config carries a deprecated `version` key.
- **Today's report** holds many runs, including failed ones; the plugin never rewrites (ADR 0042).
- **QDAC-II load:** driving the 50 Ω OPX input from the QDAC (L2-1) needs the load check in BENCH.md § L2.
- **OPX results:** one frame per result at job end; maps fill line by line (one stage per stepped point).
- **OPX `drive`:** not supported on the LF-FEM stage.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human, at the bench:**
1. Merge the PR.
2. The first sweep in the browser on the real stand, with the cable still on OPX ao1 → ai1: a stage sweep
   stepping ao1 and measuring ai1 is a self-loopback the whole control path can run on
   (`uv run python -m qdt_server --stand bench.stand.json --device-id <id> --ui apps/flightdeck/dist`).
   The map should be a plane in the pulse amplitude, now in volts.
3. L2-1 wiring per BENCH.md (QDAC DC + OPX pulse through the bias tee into ai1) once the bias tee's
   model is recorded in BENCH.md.

**Then (sessions):** L2-1 with the plane fit and L2-3 with the single exponential as curated
`qdt-analysis` methods; a hardware OPX-input row for the conformance suite; the QDAC current-sense range
on the channel declaration; Flight Deck time-series view (below); close Step 5.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:** a chop's difference is recorded (0037); additive changes without a version bump are
  accepted (0037); the operating point comes before Step 5 (0038); wall-clock CI gates are advisory
  (0039); no surrogate DUT (0040); drivers first, simple; fits later (0041); bench reports write
  themselves (0042); USB serial counts for the QDAC-II (0043); drivers are recreated here rather than
  adapted from QCoDeS, an adapter only if breadth is ever needed (discussion, no ADR); the OPX input
  constants are measured, not assumed (0044).
- **2026-10-14, tabled for later:** Flight Deck should also visualise time-series data, the bench scope's
  records first and then any instrument that can represent a time series (the OPX input, an SMU trace).
  The `Dataset` contract already carries (record, time) variables on a declared grid (ADR 0015), so this
  is a renderer in `apps/flightdeck` (a trace view beside the map view, picking a record), not a schema
  change. Not scheduled; candidate for Step 6 or a Flight Deck session after Step 5 closes.

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
- When the Flight Deck time-series view is scheduled.
