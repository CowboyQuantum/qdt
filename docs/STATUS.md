# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/single-exponential` (PR against `main`; the human merges). PRs #25–#37 merged 2026-10-14/15.
**Last session:** 2026-10-15, session 14 of Step 5, not at the bench. **The curated single exponential is
written** (`qdt_analysis.exponential.fit_exponential`, ADR 0046): `y = offset + amplitude·exp(−(t − t_start)/tau)`
by nonlinear least squares over a window anchored on a detected edge (the centre of the strongest part of the
first half-maximum run of the smoothed slope), moved by `skip` and clipped by `span`; `tau`, `amplitude`,
`offset` with standard errors, `residual_rms`, `r2`; `failed` below `min_r2` (0.5), with no edge, or with
fewer than four points after it; two `marker` overlays on the time coordinate (the edge, one τ later); the
fitted curve and residual over the record's time axis as the output payload. In the server catalogue with
`applies_to = "trace_1d"`, a value added to the frozen `MethodSpec` literal without a version bump (ADR 0037's
precedent). Thirteen L0 tests: a sharp-edge decay and a slow-onset approach recovered within standard errors,
a drooping pulse where the first edge wins and `span` keeps the falling edge out, `skip`, averaged records
with missing samples, a `WaveformSense`-shaped record through `assemble`, and **the real Probe 03 combiner
step** (`bench/fixtures/probe03/step_qdac.npz`): τ = 8.1 ms by this method, 7.9 ms by the probe's 10–90 % fit.
Both Step 5 fits now exist; both L2 runs that use them wait on the bench. Bench:
- QDAC-II (Ethernet, fixed address; USB serial also works, ADR 0043);
- Keithley 2450 and InfiniiVision HD304MSO on self-assigned addresses (mDNS finds them);
- OPX1000 with LF-FEMs;
- the combiner board (Probe 03) standing in for the bias tee.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ definition → hardware → Flight Deck → registry works on an OPX-only stand (session 11); the plane fit (session 13) has not yet run on a hardware record. L2-1's sink must be high-impedance: **a buffer before the OPX input, or the scope as the sink** (human decision) |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance; L1 rows 1–3); Probes 02 and 03 in their docs and fixtures |

## Done
- Steps 0–4b DONE. ADR 0001–0046. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036; amended additively by 0046).
- **Drivers (ADR 0041),** all four proven on hardware; OPX input constants measured (ADR 0044); OPX
  resolves logical channel names; `play` on a non-sticky twin element; `open_visa` retries a connect;
  `build_backends` closes partial builds and names the failing instrument.
- **Control path on hardware (session 11):** `qdt-server --stand` runs stage sweeps on the OPX; records
  in the registry; Flight Deck draws them; a restart reuses the registered device.
- **L1 complete (sessions 7–9):** `bench/test_l1_loopback.py`, `bench/conftest.py` fixtures.
- **Probe 02 (session 10):** OPX input calibration. **Probe 03 (session 12):** the combiner board;
  `bench/probes/probe03/combiner_probe.py`, fixtures in `bench/fixtures/probe03/`.
- **Curated methods** (`qdt_server.catalogue`): charge transitions (0029), Coulomb diamonds (0030),
  plane fit (0045, session 13), **single exponential (0046, session 14)**.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`.
- 347 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 11
  hardware-only in `bench/`; Flight Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/single-exponential` awaits the human.

## Known broken / not yet real
- **L2-1's sink:** the combiner's ≈ 25 kΩ output cannot drive the OPX's 50 Ω input (0.5 mV per volt
  arrived). Options: a unity-gain buffer at the board output (keeps L2-1 as the step defines it), the
  scope's 1 MΩ as the sink (then the OPX does not read the result), or a low-impedance rebuild of the
  board (fast, but a different board). Human decision.
- **DC sweeps through the combiner must settle ≥ 50 ms per step** (20 Hz low-pass); set
  `ChannelMap.settle_s` on the QDAC channel in the stand file for L2-1.
- **No waveform-capture activity in `SweepDefinition`:** the server cannot run a scope capture, so
  L2-3's record cannot come through the control path yet. The L2-3 bench test calls `WaveformSense.arm`
  directly and builds the record as Probe 03 did (`combiner_probe.record`), or Step 5 grows the activity.
- **Flight Deck offers every method on every record** (`applies_to` is not read): the exponential on a
  map, or the plane on a trace, fails with a 400 naming the shape. Filtering belongs with the time-series
  view (tabled), which is also what will draw the exponential's markers and output curve.
- **The exponential's edge detector is a heuristic** (ADR 0046): fixed smoothing width, first half-max
  run; a glitch steeper than the edge or an edge in the last three samples fails it. `amplitude` is
  referenced to the window's start (`attrs.t_start`), not to the physical onset (`attrs.t_edge`).
- **The plane fit is ordinary least squares, not robust** (ADR 0045); look at the residual output. The
  L2-1 bench test that calls it is not written.
- **No hardware `WaveformSense` row for the OPX input** in the conformance suite (ADR 0044); a looped-
  waveform row for `WaveformSource` on hardware would also have caught the sticky bug.
- **OPX input offset** −1.7 mV at 0 V in, not applied.
- **QDAC-II outputs can come up dead** (firmware 14-1.70): `*RST` fixes it; verify one channel first.
- **QDAC-II current readout** in the HIGH sense range hides a 1 MΩ load; `SENS<n>:RANG LOW` at 0 V.
- **Link-local addresses move** (2450, scope); `dns-sd -B _scpi-raw._tcp local.` finds them. The Mac
  sometimes routes a 169.254 host via Wi-Fi (`route -n get <ip>`); `sudo route delete <ip>` clears it.
- **HD3 sockets:** VXI-11 refuses intermittently; the socket form sometimes times out the first connect.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **Bench network:** the Mac's dock adapter needs aliases on the 10.20 subnet (`netmask` spelled out)
  and its 169.254 self-assigned address; its 10.20 alias has a /8 mask by accident.
- **qm-qua deprecation:** the OPX driver's QUA config carries a deprecated `version` key.
- **Today's report** holds many runs, including failed ones; the plugin never rewrites (ADR 0042).
- **OPX results:** one frame per result at job end; maps fill line by line (one stage per stepped point).
- **OPX `drive`:** not supported on the LF-FEM stage.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human (at the bench):**
1. Merge the PR.
2. Decide L2-1's sink: a buffer at the combiner output into the OPX input (the step as written), or the
   scope (then L2-1 is restated: the OPX plays, the scope reads, the plane fit runs on the scope's
   record). Say which; a session wires the stand file and the sweep accordingly.
3. If a buffer: put it in, keep QDAC ch01 and OPX ao1 on the board, board out → buffer → OPX ai1.

**Then (bench sessions):**
- **L2-1:** the sweep through the server with `settle_s = 0.05` on the QDAC channel, the plane fit run
  on its record from Flight Deck, the overlay drawn, the bench test in `bench/` asserting `slope_row`
  and `slope_col` against Probe 03's division and pulse-side gain.
- **L2-3:** a long OPX pulse into the combiner's pulse input, the output on the scope at 1 MΩ, captured
  through `WaveformSense.arm` on a `(record, t)` Dataset, `fit_exponential` with `span` shorter than the
  pulse, `tau` asserted against Probe 03 (the DC side's 7.9 ms is the oracle if the QDAC steps; the pulse
  side is multi-exponential and will show it in the residual). The bench report records both.
- Then: a hardware `WaveformSource`/`WaveformSense` row for the OPX in the conformance suite; the Flight
  Deck time-series view (draws scope records, the exponential's markers and output curve; filters methods
  by `applies_to`); close Step 5.

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
  first, then any instrument with a time series). A renderer, not a schema change.
- **2026-10-15:** the single exponential is written off the bench (session 14); the human continues the
  bench tests (L2-1 sink, L2-3) at the lab.

## Decisions pending
- L2-1's sink: buffer before the OPX input, or the scope.
- Whether L2-3's record comes through a new waveform-capture activity in `SweepDefinition` (the control
  path) or directly through `WaveformSense.arm` in the bench test (as Probe 03 did).
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
- When the Flight Deck time-series view is scheduled.
