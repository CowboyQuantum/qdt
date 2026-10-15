# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/waveform-capture` (PR against `main`; the human merges). PRs #25–#38 merged 2026-10-14/15.
**Last session:** 2026-10-15, session 15 of Step 5, not at the bench. Two human decisions landed: **the
scope is L2-1's sink** (L2-1 restated in BENCH.md: QDAC DC × OPX pulse through the combiner, read by the
scope; the plane fit on its record) and **waveform capture is a server feature** (ADR 0047), not a bench
shortcut. Built: `SweepDefinition.captured` (`CapturedWaveform`: channel, `start_s`, `stop_s`, `num`,
`records`; additive, no version bump), compiled to a variable over the stepped axes, an optional `record`
dim and a time axis (`time`, or `<name>_time` when grids differ), executed as a `(record, time)` slab per
stepped point through `WaveformSense.arm` and re-keyed like stage frames; a **simulated scope** on the
server's stand (`scope`/`scope1`) recording a droop set by run options `tau_s`, `droop_v`, `scope_noise_v`
(`SimulatedWaveformSense` takes a `response` callable; `exponential_decay`, `low_pass_step`); Flight Deck's
**capture** sweep kind, stored record traces drawn as traces (`chooseView` reads coordinates, not only
sizes), traces drawn on the 2-D overlay canvas with 1-coordinate markers as rules — which also fixed a
latent bug: a trace shown after a heatmap on the same page drew nothing (the WebGL context refused a 2-D
one). L0 model of L2-3: an API test (capture → record → `fit_exponential`, τ within 2 %) and an e2e test
(the UI crafts the capture, sees a trace, runs the exponential, sees its edge and τ rules). Bench:
- QDAC-II (Ethernet, fixed address; USB serial also works, ADR 0043);
- Keithley 2450 and InfiniiVision HD304MSO on self-assigned addresses (mDNS finds them);
- OPX1000 with LF-FEMs;
- the combiner board (Probe 03) standing in for the bias tee.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ the control path works on hardware (session 11, OPX loopback); L2-1 is restated with the scope as sink (BENCH.md) and the capture path it needs exists on simulated backends (session 15); the bench run is next |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance; L1 rows 1–3); Probes 02 and 03 in their docs and fixtures |

## Done
- Steps 0–4b DONE. ADR 0001–0047. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037, 0038 and 0047), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036; amended additively by 0046).
- **Drivers (ADR 0041),** all four proven on hardware; OPX input constants measured (ADR 0044); OPX
  resolves logical channel names; `play` on a non-sticky twin element; `open_visa` retries a connect;
  `build_backends` closes partial builds and names the failing instrument.
- **Control path on hardware (session 11):** `qdt-server --stand` runs stage sweeps on the OPX; records
  in the registry; Flight Deck draws them; a restart reuses the registered device.
- **Waveform capture through the control path (session 15, ADR 0047)** on simulated backends; the
  server's simulated stand has a scope.
- **L1 complete (sessions 7–9):** `bench/test_l1_loopback.py`, `bench/conftest.py` fixtures.
- **Probe 02 (session 10):** OPX input calibration. **Probe 03 (session 12):** the combiner board;
  `bench/probes/probe03/combiner_probe.py`, fixtures in `bench/fixtures/probe03/`.
- **Curated methods** (`qdt_server.catalogue`): charge transitions (0029), Coulomb diamonds (0030),
  plane fit (0045), single exponential (0046).
- **Bench reports (ADR 0042):** `scripts/bench_report.py`.
- 352 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 11
  hardware-only in `bench/`; Flight Deck 71 unit tests and 5 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/waveform-capture` awaits the human.

## Known broken / not yet real
- **L2-1 and L2-3 have not run on the bench** as capture sweeps. The stand file needs the scope's entry
  (`waveform_sense`, a voltage channel on its input) and `settle_s = 0.05` on the QDAC channel; the OPX
  pulse train is played beside the sweep with `WaveformSource.play` (nothing in a sweep plays a waveform
  yet); the scope's trigger is set on the instrument, not by the sweep.
- **Captures of one point are sequential**, one channel per capture; two channels on one trigger need a
  multi-variable `arm` (a protocol change, ADR 0021).
- **A 3-D capture variable (stepped axis, record, time) has no Flight Deck view**; records > 1 with a
  stepped axis is for the registry and the analysis.
- **Flight Deck offers every method on every record** (`applies_to` is not read): the exponential on a
  map, or the plane on a trace, fails with a 400 naming the shape. The trace view has no axes or labels
  yet and does not draw an analysis output curve beside the trace.
- **The exponential's edge detector is a heuristic** (ADR 0046); `amplitude` is referenced to the window's
  start, not to the physical onset.
- **The plane fit is ordinary least squares, not robust** (ADR 0045); look at the residual output.
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
**Human:** merge the PR.

**Then (bench sessions, in order):**
1. **Stand file:** add the scope as a `waveform_sense` instrument with a voltage channel on its input
   (`scope1`); set `settle_s = 0.05` on QDAC ch01. Wire QDAC ch01 → board DC in, OPX ao1 → board pulse in,
   board out → scope ch1 (DC, 1 MΩ). Set the scope's trigger on the pulse.
2. **L2-3:** play a long OPX pulse train with `WaveformSource.play`; run a capture sweep (no axis,
   `scope1`, a window shorter than the pulse) through `qdt-server --stand`; watch the trace in Flight
   Deck; run the single exponential from Flight Deck; the bench test in `bench/` asserts `tau` against
   Probe 03 (the DC side's 7.9 ms if the QDAC steps; the pulse side is multi-exponential and shows it in
   the residual). The report records it.
3. **L2-1 (restated):** a capture sweep with the QDAC level as the outer axis; the plateau level per
   (V_DC, V_pulse) against Probe 03's division (2.589 into 1 MΩ) and pulse-side gain; the plane fit on
   the derived map or on a (V_DC, time) record with a fixed pulse amplitude; the overlay drawn; the
   bench test asserts `slope_row` and `slope_col`.
4. Then: a hardware `WaveformSource`/`WaveformSense` row for the OPX in the conformance suite; the Flight
   Deck time-series view's remainder (axes, `applies_to` filter, output curve beside the trace); close
   Step 5.

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
  sink**; **waveform capture is a server feature** the human wants to keep, so the record type is
  identified from the Dataset's shape and the plot is cohesive with the heatmap (session 15, ADR 0047).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
- Whether a sweep should also *play* a waveform at every point (a `PlayedWaveform` activity) or L2-3 keeps
  playing its pulse train beside the sweep.
- When the Flight Deck time-series view's remainder (axes, `applies_to` filter, output curve) is scheduled.
