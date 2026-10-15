# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS;
the exit run exists, the step closes after the human's review).
**Branch:** `step-5/l2-capture-bench` (PR against `main`; the human merges). PRs #25–#39 merged 2026-10-14/15.
**Last session:** 2026-10-15, session 15 (bench, afternoon). **All three L2 rows pass on hardware through
the control path** (`bench/test_l2_capture.py`): the human's scope-as-sink decision, the capture path of
ADR 0047 and both curated fits, on the real stand: QDAC ch01 → combiner DC in, OPX ao1 → combiner pulse in,
board out → scope ch1 at 1 MΩ, with `qdt-server --stand` owning the QDAC and the scope and the OPX pulse
train played beside the sweep. L2-1 DC: plane `slope_row` 0.385–0.386 V/V against 1/2.589 (Probe 03),
r² 0.9999; with the pulse on: unchanged, plateau gain 0.595 against 0.61 from Probe 03's record. L2-3:
τ 2.0 µs against 1.86 µs by the same fit on Probe 03's record. Every run recorded, overlaid in Flight
Deck. **Probe 04** (the human's question: how fast can the QDAC be stepped?): the output edge follows
`set()` by < 4.5 ms (USB serial; steady to ±0.2 ms), settles to 1 % in 3 µs and to 0.1 % in < 1 ms for
any step to 1 V; **`settle_s = 0.01` direct, `0.05` through the combiner**; the output filter setting
(DC/MED/HIGH) made no difference to the step on this unit. Bench:
- QDAC-II (USB serial today; Ethernet also works, ADR 0043), ch01 → combiner, ch02 → scope ch2 (Probe 04);
- Keithley 2450 and InfiniiVision HD304MSO on self-assigned addresses (mDNS finds the 2450; the scope
  answers TCP but not ping);
- OPX1000 with LF-FEMs (the dock adapter needs its 10.20 alias after a reboot: `sudo ifconfig en11 alias
  10.20.150.250 netmask 255.255.255.0`);
- the combiner board (Probe 03) standing in for the bias tee.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ✔ 2026-10-15: capture sweeps through the server on the real stand, recorded, fitted from the API, overlays replayed to Flight Deck; `bench/test_l2_capture.py` (3 rows) |
| bench report committed | ✔ `bench/reports/2026-10-15-step5.md` (L2 rows); `2026-10-14-step5.md` (conformance; L1 rows 1–3); Probes 02–04 in their docs and fixtures |

## Done
- Steps 0–4b DONE. ADR 0001–0047. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038 and 0047), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036; amended additively by 0046).
- **Drivers (ADR 0041),** all four proven on hardware; OPX input constants measured (ADR 0044).
- **Control path on hardware:** stage sweeps on the OPX (session 11); capture sweeps on the QDAC + scope
  stand (session 15, ADR 0047).
- **L1 complete (sessions 7–9); L2 complete (session 15):** `bench/test_l1_loopback.py`,
  `bench/test_l2_capture.py`, `bench/scope_accuracy.py` (the HD3 datasheet formula, shared),
  `bench/conftest.py` fixtures (the front-panel fixture takes a trigger coupling).
- **Probes:** 02 (OPX input calibration), 03 (the combiner board), **04 (QDAC settling)**.
- **Curated methods:** charge transitions (0029), Coulomb diamonds (0030), plane fit (0045), single
  exponential (0046); both fits now proven on hardware records.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`.
- 352 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 14
  hardware-only in `bench/`; Flight Deck 71 unit tests and 5 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/l2-capture-bench` awaits the human.

## Known broken / not yet real
- **The QDAC-II's output filter setting had no effect on the step** (Probe 04; firmware 14-1.70): DC,
  MED and HIGH all gave a 1.9 µs edge, and MED and HIGH pass a 100 kHz sine alike. The firmware knows the
  setting (it refuses the sine generator under DC). Verify with the front panel or QDevil before a stand
  file assumes a low-noise filter on a held gate. The driver never sets the filter.
- **The command latency bound is poll-limited** (< 4.5 ms, the scope's query round trip); the QDAC's
  serial query round trip is 16 ms, so an acknowledgement in `set` is not worth it. The Ethernet link
  may be faster (not measured).
- **Nothing in a sweep plays a waveform:** L2-3's OPX pulse train is played beside the sweep by the
  test; the scope's trigger is set on the instrument (BENCH.md records the convention).
- **A sweep leaves its last level on the QDAC** (ADR 0038 holds levels, never zeroes them); a capture
  that wants 0 V holds it through `levels`. Whether a sweep should return to a rest level is undecided.
- **Captures of one point are sequential**, one channel per capture (ADR 0047).
- **A 3-D capture variable (stepped axis, record, time) has no Flight Deck view.**
- **Flight Deck offers every method on every record** (`applies_to` is not read); the trace view has no
  axes or labels and does not draw an analysis output curve beside the trace.
- **The exponential's edge detector is a heuristic** (ADR 0046); `amplitude` is referenced to the
  window's start. **The plane fit is ordinary least squares** (ADR 0045).
- **No hardware `WaveformSense` row for the OPX input** in the conformance suite (ADR 0044).
- **OPX input offset** −1.7 mV at 0 V in, not applied.
- **QDAC-II outputs can come up dead** (firmware 14-1.70): `*RST` fixes it; verify one channel first.
- **QDAC-II current readout** in the HIGH sense range hides a 1 MΩ load; `SENS<n>:RANG LOW` at 0 V.
- **Link-local addresses move** (2450, scope); `dns-sd -B _scpi-raw._tcp local.` finds the 2450; the
  scope is found in the ARP table and answers TCP on 5025 but not ping. The HD3 refuses a socket for a
  few seconds after one closes (retry). Its SCPI is slow: a query round trip is 4.5 ms, a write with
  `*OPC?` 44 ms; a single-shot left waiting blocks `*OPC?` (send `:STOP` first).
- **Bench network:** the dock adapter loses its 10.20 alias on reboot (`sudo ifconfig en11 alias ...`).
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecation:** the OPX driver's QUA config carries a deprecated `version` key; `job.halt` is
  deprecated for `job.cancel`.
- **Today's report** holds many runs, including failed ones; the plugin never rewrites (ADR 0042).
- **OPX results:** one frame per result at job end; maps fill line by line.
- **OPX `drive`:** not supported on the LF-FEM stage.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human:**
1. Merge the PR.
2. Review the Step 5 exit: the three criteria are met. Say whether Step 5 closes now or after the
   remaining rows (a hardware `WaveformSource`/`WaveformSense` conformance row for the OPX; L2-2, the
   current readout into the scope's 1 MΩ, which no test has run).
3. Verify the QDAC-II output filter on the front panel (Probe 04 finding 1).

**Then (sessions):** close Step 5 (status, step index, DEVELOPMENT_PLAN §7.2 row); the OPX conformance
rows; L2-2; the Flight Deck time-series view's remainder (axes, `applies_to` filter, output curve);
Step 6 planning (ADR: a `PlayedWaveform` activity and sub-ms stepping on the sequencer, informed by
Probe 04).

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:** a chop's difference is recorded (0037); additive changes without a version bump are
  accepted (0037); the operating point comes before Step 5 (0038); wall-clock CI gates are advisory
  (0039); no surrogate DUT (0040); drivers first, simple; fits later (0041); bench reports write
  themselves (0042); USB serial counts for the QDAC-II (0043); drivers are recreated here rather than
  adapted from QCoDeS (discussion, no ADR); the OPX input constants are measured, not assumed (0044);
  the combiner board stands in for the bias tee and is characterised by a probe before it is used
  (Probe 03, no ADR: BENCH.md records the part); the plane fit is written ahead of the sink decision
  (session 13).
- **2026-10-14, tabled for later:** Flight Deck should also visualise time-series data (scope records
  first, then any instrument with a time series). A renderer, not a schema change. (Session 15 did the
  first part: record traces draw as traces with markers; axes, labels and the method filter remain.)
- **2026-10-15:** the single exponential is written off the bench (session 14); **the scope is L2-1's
  sink**; **waveform capture is a server feature** the human wants to keep (ADR 0047); the human asked
  how fast the QDAC can be stepped in an untriggered sweep (Probe 04: the serial latency, not the
  analog settling, is the wait).

## Decisions pending
- Whether Step 5 closes now (exit criteria met) or after the OPX conformance rows and L2-2.
- Whether a sweep should also *play* a waveform at every point (a `PlayedWaveform` activity) or L2-3
  keeps playing its pulse train beside the sweep.
- Whether a sweep returns the stepped channels to a rest level at its end.
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
- When the Flight Deck time-series view's remainder (axes, `applies_to` filter, output curve) is scheduled.
