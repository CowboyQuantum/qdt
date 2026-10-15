# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS;
every row of the ladder has run on hardware; the step closes on the human's word).
**Branch:** `step-5/opx-conformance-l2-2` (PR against `main`; the human merges). PRs #25–#40 merged 2026-10-14/15.
**Last session:** 2026-10-15, session 16 (bench). **The OPX1000 passes every conformance row** (source 5/5,
sense 6/6, sequencer 7/7): registered through its logical-name resolution; the suite's test waveform is now
0.1 V (the LF-FEM's direct mode is ±0.5 V) and its record grid starts at the trigger (the OPX opens its
readout window there; pre-trigger samples are a scope's ability, not part of the protocol); a new suite
test, a second `play` replaces the first. **L2-2 passes** (`bench/test_l2_current_readout.py`): the SMU
into the scope's 1 MΩ reads −1.9989, −0.9995, +0.9994, +1.9988 µA at ±2 and ±1 V (R = 1.0006 MΩ), with its
current measure range held at 10 µA; the QDAC into the scope's 50 Ω reads ±1 mA in its HIGH range after a
+73 µA zero. Three QDAC-II findings for QDevil (BENCH.md quirks): the LOW sense range measures nothing on
this unit (≈ 2 nA for 1 µA and for 1 mA alike), ch02 went dead after Probe 04 and `*RST` did not revive it,
and together with Probe 04's filter finding every relay-switched output setting looks stuck; also the
output impedance is 50 Ω (half the setpoint into 50 Ω). Bench:
- QDAC-II (USB serial), ch01 → combiner, **ch02 dead**, ch03 → scope ch2 (L2-2);
- Keithley 2450 on the switch (its cable to scope ch3 was moved to the QDAC); HD304MSO answers TCP, not ping;
- OPX1000 with LF-FEMs (dock alias `sudo ifconfig en11 alias 10.20.150.250 netmask 255.255.255.0`);
- the combiner board (Probe 03) standing in for the bias tee.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 18/18 (all three capabilities, 2026-10-15), Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ✔ 2026-10-15 (session 15); L2-2 and L2-3 also pass |
| bench report committed | ✔ `bench/reports/2026-10-15-step5.md`; Probes 02–04 in their docs and fixtures |

## Done
- Steps 0–4b DONE. ADR 0001–0047. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038 and 0047), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036; amended additively by 0046).
- **Drivers (ADR 0041),** all four proven on hardware in every capability; OPX input constants (ADR 0044).
- **Control path on hardware:** stage sweeps on the OPX (session 11); capture sweeps on the QDAC + scope
  stand (session 15, ADR 0047).
- **L1 complete; L2 complete (L2-1, L2-3 session 15; L2-2 session 16):** `bench/test_l1_loopback.py`,
  `bench/test_l2_capture.py`, `bench/test_l2_current_readout.py`, `bench/scope_accuracy.py`.
- **Probes:** 02 (OPX input calibration), 03 (the combiner board), 04 (QDAC settling).
- **Curated methods:** charge transitions (0029), Coulomb diamonds (0030), plane fit (0045), single
  exponential (0046); both fits proven on hardware records.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`.
- 353 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 71 unit tests and 5 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/opx-conformance-l2-2` awaits the human.

## Known broken / not yet real
- **QDAC-II (firmware 14-1.70), three findings for QDevil:** the output filter setting changes nothing
  (Probe 04); the LOW current-sense range reads ≈ 2 nA for any current; ch02 is dead (0 V for every
  setpoint, setpoint reported, `*RST` no cure). The HIGH range works (zero ≈ +73 µA, 2–3 % low); the
  driver never sets filter or range. Power-cycle the unit when the bench allows.
- **The QDAC's output impedance is 50 Ω:** a 50 Ω load halves the level; high-impedance loads are fine.
- **The 2450 autoranges its current measurement to 10 nA at 0 V** and then charges the cable at 10 nA:
  hold the range (`:SENS:CURR:RANG`) in a stand whose SMU drives a capacitive line. How a sense range is
  declared is a pending decision (channel map vs. inferred).
- **The command latency bound is poll-limited** (< 4.5 ms); the Ethernet link is not measured.
- **Nothing in a sweep plays a waveform:** L2-3's OPX pulse train is played beside the sweep.
- **A sweep leaves its last level on the QDAC** (ADR 0038); a capture that wants 0 V holds it through `levels`.
- **Captures of one point are sequential**, one channel per capture (ADR 0047). **A 3-D capture variable
  has no Flight Deck view.** **Flight Deck offers every method on every record**; the trace view has no
  axes or labels and no output curve.
- **The exponential's edge detector is a heuristic** (ADR 0046). **The plane fit is ordinary least
  squares** (ADR 0045).
- **OPX input offset** −1.7 mV at 0 V in, not applied. **OPX `drive`:** not supported on the LF-FEM
  stage. **OPX results:** one frame per result at job end.
- **QDAC-II outputs can come up dead after a power cycle** (`*RST` fixes that case).
- **Link-local addresses move**; the scope answers TCP on 5025 but not ping, refuses a socket for a few
  seconds after one closes, and its SCPI is slow (query 4.5 ms, write with `*OPC?` 44 ms; a waiting
  single-shot blocks `*OPC?`: send `:STOP` first).
- **Bench network:** the dock adapter loses its 10.20 alias on reboot.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecations:** the QUA config's `version` key; `job.halt` for `job.cancel`.
- **Today's report** holds many runs, including failed ones; the plugin never rewrites (ADR 0042).
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human:**
1. Merge the PR.
2. Close Step 5 or name what is still missing: every exit criterion is met and every ladder row has run
   on hardware. A session then marks the step DONE (status, `docs/steps/README.md`, DEVELOPMENT_PLAN
   §7.2) and opens Step 6's file.
3. Report the three QDAC-II findings to QDevil; power-cycle the unit; check whether ch02 returns.

**Then (sessions):** Step 6 planning (ADRs: a `PlayedWaveform` activity; sub-ms stepping on the sequencer,
informed by Probe 04; how a sense range is declared); the Flight Deck time-series view's remainder (axes,
`applies_to` filter, output curve beside the trace); a Probe on the QDAC's Ethernet latency if Step 6 needs
the bound tightened.

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
  how fast the QDAC can be stepped in an untriggered sweep (Probe 04); the human chose to finish the OPX
  conformance rows and L2-2 before closing Step 5 (session 16); the combiner wiring stays intact
  throughout, L2-2 and Probe 04 use spare QDAC channels and scope inputs.

## Decisions pending
- Closing Step 5 (every criterion met) and opening Step 6.
- Whether a sweep should also *play* a waveform at every point (a `PlayedWaveform` activity).
- Whether a sweep returns the stepped channels to a rest level at its end.
- How a sense range is declared (channel map vs. inferred): the 2450's autorange and the QDAC's LOW range
  both argue for declaring it.
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- When the Flight Deck time-series view's remainder (axes, `applies_to` filter, output curve) is scheduled.
