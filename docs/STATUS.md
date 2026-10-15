# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/plane-fit` (PR against `main`; the human merges). PRs #25–#36 merged 2026-10-14.
**Last session:** 2026-10-14, session 13 of Step 5, not at the bench. **The curated plane fit is written**
(`qdt_analysis.plane.fit_plane`, ADR 0045): ordinary least squares over the finite points with standard
errors, `slope_row`, `slope_col`, `offset`, `isoline_slope`, `residual_rms`, `r2`; `failed` when the plane
explains less than `min_r2` (0.5) of the variance or the map is constant; `n_isolines` (8) iso-lines as
`line` annotations clipped to the window and labelled with their level; the fitted plane and residual as
the output payload. In the server catalogue, so Flight Deck's method list offers it. Thirteen L0 tests:
a synthetic plane with Probe 03's coefficients recovered within standard errors, a plane through the real
sweep path (two simulated levels summed by a simulated sense: the L0 model of L2-1), iso-line geometry in
every orientation, leading dims and missing points, noise and constant maps fail. L2-1's sink decision
is still open. Bench:
- QDAC-II (Ethernet, fixed address; USB serial also works, ADR 0043);
- Keithley 2450 and InfiniiVision HD304MSO on self-assigned addresses (mDNS finds them);
- OPX1000 with LF-FEMs;
- the combiner board (Probe 03) standing in for the bias tee.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ definition → hardware → Flight Deck → registry works (OPX loopback, session 11); the plane fit for the overlay is written (session 13). L2-1's sink must be high-impedance: **a buffer before the OPX input, or the scope as the sink** (human decision) |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance; L1 rows 1–3); Probes 02 and 03 in their docs and fixtures |

## Done
- Steps 0–4b DONE. ADR 0001–0045. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** all four proven on hardware; OPX input constants measured (ADR 0044); OPX
  resolves logical channel names; `play` on a non-sticky twin element; `open_visa` retries a connect;
  `build_backends` closes partial builds and names the failing instrument.
- **Control path on hardware (session 11):** `qdt-server --stand` runs stage sweeps on the OPX; records
  in the registry; Flight Deck draws them; a restart reuses the registered device.
- **L1 complete (sessions 7–9):** `bench/test_l1_loopback.py`, `bench/conftest.py` fixtures.
- **Probe 02 (session 10):** OPX input calibration. **Probe 03 (session 12):** the combiner board;
  `bench/probes/probe03/combiner_probe.py`, fixtures in `bench/fixtures/probe03/`.
- **Curated methods** (`qdt_server.catalogue`): charge transitions (0029), Coulomb diamonds (0030),
  **plane fit (0045, session 13)**.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`.
- 333 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 11
  hardware-only in `bench/`; Flight Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/plane-fit` awaits the human.

## Known broken / not yet real
- **L2-1's sink:** the combiner's ≈ 25 kΩ output cannot drive the OPX's 50 Ω input (0.5 mV per volt
  arrived). Options: a unity-gain buffer at the board output (keeps L2-1 as the step defines it), the
  scope's 1 MΩ as the sink (then the OPX does not read the result), or a low-impedance rebuild of the
  board (fast, but a different board). Human decision.
- **DC sweeps through the combiner must settle ≥ 50 ms per step** (20 Hz low-pass); set
  `ChannelMap.settle_s` on the QDAC channel in the stand file for L2-1.
- **The plane fit is ordinary least squares, not robust** (ADR 0045): a map that is half plane, half
  structure can pass `min_r2` with a biased plane; look at the residual output. The L2-1 bench test that
  calls it is not written.
- **Single exponential not written** (L2-3; the combiner's own droop, τ = 7.9 ms, is the real exponential).
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
**Human:**
1. Merge the PR.
2. Decide L2-1's sink: a buffer at the combiner output into the OPX input (the step as written), or the
   scope (then L2-1 is restated: the OPX plays, the scope reads, the plane fit runs on the scope's
   record). Say which; a session wires the stand file and the sweep accordingly.
3. If a buffer: put it in, keep QDAC ch01 and OPX ao1 on the board, board out → buffer → OPX ai1.

**Then (sessions):** the L2-1 sweep through the server with `settle_s = 0.05` on the QDAC channel, the
plane fit run on its record from Flight Deck, the overlay drawn, the bench test in `bench/` asserting
`slope_row` and `slope_col` against Probe 03's division and pulse-side gain; the single exponential and
L2-3; a hardware `WaveformSource`/`WaveformSense` row for the OPX in the conformance suite; the Flight
Deck time-series view; close Step 5.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:** a chop's difference is recorded (0037); additive changes without a version bump are
  accepted (0037); the operating point comes before Step 5 (0038); wall-clock CI gates are advisory
  (0039); no surrogate DUT (0040); drivers first, simple; fits later (0041); bench reports write
  themselves (0042); USB serial counts for the QDAC-II (0043); drivers are recreated here rather than
  adapted from QCoDeS (discussion, no ADR); the OPX input constants are measured, not assumed (0044);
  the combiner board stands in for the bias tee and is characterised by a probe before it is used
  (Probe 03, no ADR: BENCH.md records the part); the plane fit is written in this session on the human's
  word, ahead of the sink decision (session 13).
- **2026-10-14, tabled for later:** Flight Deck should also visualise time-series data (scope records
  first, then any instrument with a time series). A renderer, not a schema change.

## Decisions pending
- L2-1's sink: buffer before the OPX input, or the scope.
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
- When the Flight Deck time-series view is scheduled.
