# Step 5 — Instrument drivers (the last mile)

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Real drivers behind the protocols. Everything above already works against `Simulated*`; this step proves the simulated backends were honest. First `bench/` reports.

## Schema slice
None new. `InstrumentConfig` gains vendor address fields only if required (minor bump).

## Deliverables
- `docs/BENCH.md` complete, including the bias tee's and the scope's specifications for L2 (ADR 0040)
- `qdt-lab/drivers/`: OPX, QDAC-II, Keysight scope, SMU — each behind an extra (ADR 0006), each registered in the conformance parametrization
- `bench/` L1 loopback and L2 instrument-on-instrument suites; dated reports committed
- curated `qdt-analysis` methods for L2: plane fit (with iso-line overlays) and single exponential

## L0 tests (CI)
- conformance suite unchanged and green on `Simulated*`
- extras matrix green

## L1 tests (bench loopback)
- QDAC→scope, SMU→scope, OPX out→scope loopbacks with numeric oracles
- `StandConfig` validates against the enumerated bench

## L2 tests (instrument-on-instrument)
- L2-1: QDAC DC × OPX pulse through the bias tee, read by the stage `measure` on an OPX input; a plane with specified coefficients, live in Flight Deck, recorded in the registry, fitted by `qdt-analysis`, overlays drawn
- L2-2: QDAC and SMU current readout into the scope's 1 MΩ input (I = V / 1 MΩ)
- L2-3: the bias tee's droop on an OPX step, captured by the scope; single-exponential fit against its specification

## Exit criteria
- conformance suite passes on all four real instruments under `-m hardware`
- one end-to-end L2 run (L2-1): definition → hardware → Flight Deck → registry → overlay
- bench report committed

## Open decisions
- #10 surrogate DUT design — closed by ADR 0040 (no board)

## Status
IN PROGRESS (opened 2026-10-14, ADR 0041). Session 1: drivers for the QDAC-II, Keithley 2400-series,
InfiniiVision X and OPX1000. Each SCPI driver passes the conformance suite on its emulator in CI. The OPX's
QUA programs and config are validated offline by qm-qua. `qdt-server --stand` runs on a real stand, and a
CI test runs a sweep through the server on the real drivers over emulators. Remaining: the first
`-m hardware` run and its fixes, the OPX calibration constants, L1/L2 bench suites and the report, and
linear and exponential fits (asked for by the human; plane and single exponential).
Session 2 (2026-10-14, bench): first hardware contact. The OPX1000 passed all seven sequencer conformance
tests unchanged (`bench/reports/2026-10-14-step5.md`). `scripts/bench_report.py` now writes that report
from any `-m hardware` run (ADR 0042). The QDAC-II, SMU and scope await their addresses in the stand file.
Session 3 (2026-10-14, bench): the Keithley (a 2450) passes the conformance suite (5 passed, 2 single-terminal
skips) after one harness fix: the 2450 accepts one raw-socket connection at a time, so the suite's fixtures
now close every backend at teardown (`closing` in `tests/conftest.py`). The QDAC-II sits on a wire with no
DHCP and has no address yet; the scope is next.
Session 4 (2026-10-14, bench): the QDAC-II passes its three LevelSource conformance tests over the rear USB
port (`ASRL...`; ADR 0043) after the transport learned a baud rate. Its LAN got a fixed address over USB but
has not been seen on Ethernet yet (the cable was moved). Three of four instruments proven; the scope is left.
Session 5 (2026-10-14, bench): the scope (an HD304MSO, InfiniiVision HD3 series) passes all six WaveformSense
conformance tests after two driver fixes made with the emulator: the model check admits HD3, and the LEFT
timebase reference sits one division in from the screen edge, so the capture starts at position - range/10.
**All four instruments pass the conformance suite on hardware** (first exit criterion met, for the tests the
suite has today). Left: QDAC-II on Ethernet (address set, unverified), L2-1, the L1/L2 suites, the fits.
