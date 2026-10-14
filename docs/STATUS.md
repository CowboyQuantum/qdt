# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (IN PROGRESS).
**Branch:** `step-5/first-real-sweep` (PR against `main`; the human merges). PRs #25–#34 merged 2026-10-14.
**Last session:** 2026-10-14, session 11 of Step 5, at the bench. **The first sweeps on real hardware ran
through the server and Flight Deck.** Device: the OPX's own ao1 → ai1 loopback, on an OPX-only local
stand (`bench-opx.stand.json`: `P2_pulse` ao1, `P_outer` ao2 open, `sensor` ai1), because the QDAC and
the SMU had dropped off the wire by then. A 64-point line (`V_in = 1.0133 · v_p2 + 2 mV`, residual
0.5 mV) and a 16 × 32 plane (row slopes 1.016 ± 0.001 along the swept output, columns flat to 0.3 mV
along the open outer axis), both recorded in the registry at `~/.qdt/registry` and visible in Flight
Deck's dataset selector. The OPX input constants from Probe 02 make these volts. Three bugs found by the
first real run, all fixed with tests:
1. the OPX driver did not resolve the stand's **logical channel names** (`P2_pulse`) to its ports;
   the compiler hands it sequences in logical names, the emulator-backed CI path never differed;
2. a failed `build_backends` **leaked the sockets** of the drivers already built (the 2450 allows one)
   and the error did not name the instrument; `open_visa` now also retries a connect;
3. a **server restart** with the same device id failed on the later registration time.

## Step 5 exit criteria
| Criterion | State |
|---|---|
| conformance suite passes on all four real instruments under `-m hardware` | ✔ OPX1000 7/7, Keithley 2450 5/5 (+2 skips), QDAC-II 3/3, HD304MSO 6/6 (2026-10-14) |
| one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay | ◐ **definition → hardware → Flight Deck → registry works** (session 11, OPX loopback). Missing: the L2-1 wiring through the bias tee with the QDAC, and the **plane fit** as a curated method for the overlay |
| bench report committed | ✔ `bench/reports/2026-10-14-step5.md` (conformance on all four; L1 rows 1–3); Probe 02 findings. L2 to come. The server runs are in the registry, not the report |

## Done
- Steps 0–4b DONE. ADR 0001–0044. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **Drivers (ADR 0041),** all four proven on hardware: `qdevil/qdac2` (TCP or USB serial, ADR 0043),
  `keithley/k2400` (a 2450), `keysight/infiniivision` (DSOX/MSOX/HD3), `qm/opx1000` (Sequencer and
  `WaveformSource.play`; input constants measured, ADR 0044; logical channel names resolved).
  `drivers/scpi.py` retries a connect; `build_backends` closes partial builds.
- **Control path on hardware (session 11):** `qdt-server --stand <file> --device-id <id>` runs stage
  sweeps on the OPX; records land in the registry; Flight Deck draws them live. A restart reuses the
  registered device.
- **L1 complete (sessions 7–9):** `bench/test_l1_loopback.py`; `bench/conftest.py` fixtures;
  `QDT_L1_SOURCES` names cabled sources.
- **Probe 02 (session 10):** OPX input calibration; fixtures `bench/fixtures/probe02/`.
- **Bench reports (ADR 0042):** `scripts/bench_report.py`; one file per day, a section per run.
- **Extras:** `[qdac]` adds pyvisa, pyvisa-py and pyserial; `[keysight]` and `[smu]` add pyvisa and
  pyvisa-py; `[opx]` adds qm-qua 1.4.1.
- 319 Python tests (+5 Postgres-parametrized), 4 skipped, 23 hardware-only in `packages/`, 11
  hardware-only in `bench/`; Flight Deck 68 unit tests and 4 e2e.

## In flight
- Nothing uncommitted. PR for `step-5/first-real-sweep` awaits the human. The server may still be running
  on the OPX-only stand (`pkill -f "python -m qdt_server"` stops it).

## Known broken / not yet real
- **The QDAC and the SMU dropped off the wire** during session 11 (no ping, no ARP, no USB port on the
  QDAC); not diagnosed. Both must be back for L2-1. The 2450's link-local address also acquired a stale
  route via Wi-Fi on the Mac (`route -n get <ip>` said `en0`); `sudo route delete <ip>` or re-plugging
  the dock adapter clears it.
- **Plane fit not written:** the L2-1 overlay needs the curated plane method (and L2-3 the single
  exponential) in `qdt-analysis`.
- **No hardware `WaveformSense` row for the OPX input** in the conformance suite (ADR 0044).
- **OPX input offset** −1.7 mV at 0 V in, not applied; the loopback line shows +2 mV at v_p2 = 0.
- **QDAC-II outputs can come up dead** (firmware 14-1.70): `*RST` fixes it; verify one channel at the
  start of a bench session. Not a driver action.
- **QDAC-II current readout** in the HIGH sense range hides a 1 MΩ load; `SENS<n>:RANG LOW` at 0 V.
- **Link-local addresses move** (2450, scope); `dns-sd -B _scpi-raw._tcp local.` finds them.
- **HD3 sockets:** VXI-11 refuses intermittently; the socket form sometimes times out the first connect
  (now retried in `open_visa`).
- **Serial numbers:** driver errors show vendor and model only; `bench_report.py` does not redact
  `*IDN?` serials (decision pending).
- **Bench network:** the Mac's dock adapter needs aliases on the 10.20 subnet (`netmask` spelled out)
  and its 169.254 self-assigned address; its 10.20 alias has a /8 mask by accident.
- **qm-qua deprecation:** the OPX driver's QUA config carries a deprecated `version` key.
- **Today's report** holds many runs, including failed ones; the plugin never rewrites (ADR 0042).
- **OPX results:** one frame per result at job end; maps fill line by line (one stage per stepped point).
  With both axes in the stage (session 11's plane) the whole map is one job and arrives at its end.
- **OPX `drive`:** not supported on the LF-FEM stage.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.

## Next action
**Human, at the bench:**
1. Merge the PR.
2. Get the QDAC and the SMU back on the wire (check their Ethernet cables at the switch and their
   power); a session re-finds them (QDAC at its fixed address, SMU by mDNS) and updates the stand file.
3. Record the bias tee's model and specifications in `docs/BENCH.md` § L2 (human), then wire L2-1:
   QDAC ch → bias tee DC port, OPX ao1 → RF port, bias tee out → OPX ai1.

**Then (sessions):** the curated **plane fit** (iso-line overlays) in `qdt-analysis`, then L2-1 through
the server for the exit criterion; the single exponential and L2-3; a hardware OPX-input row for the
conformance suite; the QDAC current-sense range; the Flight Deck time-series view; close Step 5.

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
  records first and then any instrument that can represent a time series. The `Dataset` contract already
  carries (record, time) variables on a declared grid (ADR 0015); a renderer in `apps/flightdeck`, not a
  schema change. Candidate for Step 6 or a Flight Deck session after Step 5 closes.

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
- Whether `bench_report.py` should redact `*IDN?` serial fields.
- How the QDAC-II current-sense range is declared (channel map vs. inferred).
- When the Flight Deck time-series view is scheduled.
