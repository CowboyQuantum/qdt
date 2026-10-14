# 0041 — Step 5 drivers: one SCPI transport, an emulator per driver, the OPX building QUA from the emitted stage

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 5

## Context
The human asked for the drivers directly, kept simple: "write the driver for the instruments so that
they can generate the output signals and read them back into the correct shape for the front end to
stream and for the database to store." The bench has:
- a QDAC-II (Ethernet);
- a Keithley 2400-series SMU;
- a Keysight InfiniiVision X scope;
- an OPX1000 with LF-FEMs.

The protocols and the construction convention are frozen (ADR 0021). The drivers have to pass the
existing conformance suite, which is the spec, and must be usable before any hardware session. Probe 01
had already shown what works on this OPX (qm-qua 1.4.1, QOP 3.7.1): compile once, then int input
streams (fixed-typed ones do not compile).

## Decision
- **One small `ScpiTransport`** (`write`, `query`, `query_block`) shared by the three SCPI drivers, with
  pyvisa underneath, imported lazily. No qcodes: its dependency footprint is large, and three
  instruments need about a dozen commands each.
- **Every SCPI driver ships an emulator** in the package, next to it. The emulator rejects any command it
  does not know, so a typo fails at L0. The conformance suite runs on driver + emulator in CI, and on
  driver + instrument under `-m hardware`, with the address taken from `QDT_*_ADDRESS`.
- **The OPX builds QUA from the emitted stage.** `QuaEmitter` uses the simulated emitter's body and
  parameter scheme. At compile time `Opx1000` builds the QUA program, reading all parameters from one
  int input stream:
  - sticky elements hold levels between ops, and ops are serialised with `align()`;
  - measures integrate over the op's window;
  - `difference` and `mean`/`sum` reductions are applied to the per-shot values as they are fetched, so
    they keep ADR 0037's per-shot semantics;
  - a reopened quantum machine (because the config grew) recompiles stale handles.
- **The suite learns about single-terminal instruments.** A backend declaring `single_terminal` skips
  "channels are independent". An SMU has one terminal.
- **`qdt-server --stand <file> --device-id <id>`** runs on a real stand. It builds the stand's drivers
  once through `qdt_lab.drivers.FACTORIES`. The stand file holds addresses and is gitignored
  (`*.stand.json`); `docs/examples/bench.stand.example.json` shows the shape with placeholders.

## Consequences
- Easier:
  - The whole chain (sweep → drivers → stream → record → registry) is tested in CI on the real driver
    code (`test_a_sweep_runs_on_the_real_drivers_streams_and_records`).
  - A bench session starts from drivers that already pass the suite, so the first hardware run is about
    the instrument, not the code.
- Harder:
  - An emulator encodes our reading of the manual, so a wrong command is wrong in both places. The
    first `-m hardware` run is the real check. Every driver docstring lists its commands for that.
  - The OPX has two calibration constants in one place: `INTEGRATION_TO_VOLTS` and `RAW_ADC_TO_VOLTS`.
    Both are to be confirmed with an OPX AO → AI loopback at a known level.
  - The OPX returns a stage's results when the job finishes, one frame per result, not point by point.
    The executor runs one stage per stepped point, so a map still fills line by line.
- Must now:
  - Run the conformance suite at the bench (`uv run pytest packages/qdt-lab bench -m hardware` with the
    addresses exported) and commit the report in `bench/reports/`.
  - Fix whatever the instruments disagree with, in the driver and its emulator together.

## Alternatives considered
- **qcodes drivers** (QDAC-II, Keithley, Keysight). Rejected: they bring a large dependency tree and a
  second instrument model on top of our protocols, for a handful of SCPI commands.
- **Mock-based unit tests per driver**, instead of emulators running the conformance suite. Rejected:
  they would test our calls, not the protocol behaviour the suite specifies.
- **Recompiling the QUA program for every run with constants inlined.** Rejected: Probe 01 showed that
  compile once with an int input stream works, and it avoids a compile per stepped point.
- **Renaming every driver's channels to the suite's `ch00`/`ch01`.** Rejected: drivers keep vendor
  numbering. The test registration maps the names for the one instrument that needs it (the QDAC-II
  numbers from 1).
