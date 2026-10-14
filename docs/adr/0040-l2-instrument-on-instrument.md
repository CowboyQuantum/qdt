# 0040 — L2 is instrument-on-instrument with off-the-shelf parts, not a surrogate DUT board

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 5 entry; closes Open Decision #10; amends the L2 rung of ADR 0004's test ladder

## Context
ADR 0004 defined the ladder L0 simulated, L1 bench loopback, L2 surrogate DUT, L3 fridge. L2 was a passive
board (a resistor divider, an RC leg and a diode) with an analytic response, built and hand-characterized
before Step 5 (ADR 0007: "build the surrogate DUT by Step 5 entry"). A full board design was drafted for
Open Decision #10 (PR #24).

The human asked whether the board can be skipped: use the OPX input, the benchtop scope and the SMU to read
the outputs of the other instruments. Going through what each leg of the board was for:
- **A 2-D map in which both axes matter** (the Step 5 exit run: definition → hardware → Flight Deck →
  registry → fit → overlay).
  - A **bias tee**, a standard lab part the bench has, gives this. It combines a QDAC DC level (DC port)
    with OPX pulses (RF port) on one line: V = c_DC·V_DC + c_P·V_pulse.
  - This is the operating point plus a pulse on top (ADR 0038), wired the way a real gate is.
  - It is the same `SweepDefinition` shape as the simulator's stability diagram.
- **Current readout** (`LevelSense` in current on the QDAC and the SMU). The scope's DC-coupled 1 MΩ input
  is a specified load: I = V / 1 MΩ. It also gives ADR 0016's load-dependent `LevelSense` oracle.
- **Timing** (the RC step). The OPX → scope loopback is already L1's timing oracle. The bias tee adds a
  real single-exponential response: its droop on a long step.
- **A nonlinear response** (the diode). Nothing replaces it. The fitting code is covered by
  injection-recovery at L0, so what is lost is only "a nonlinear fit on real data before the fridge".

## Decision
Redefine **L2 as instrument-on-instrument tests using only the bench's instruments and off-the-shelf parts**
(a bias tee, the scope's 1 MΩ input). No custom board is built or maintained. Open Decision #10 is closed
("no surrogate DUT"). The concrete wiring and oracles live in `docs/BENCH.md` § L2; the Step 5 L2 tests are
these:
- **L2-1, the Step 5 exit run.** A stage sweep: outer axis the QDAC DC level into the bias tee's DC port,
  inner axis the OPX pulse amplitude into the RF port, read by the stage's `measure`. The fit is a plane,
  and its iso-lines are drawn as overlays.
- **L2-2, current readout.** A QDAC channel, then the SMU, drives the scope's 1 MΩ input. Each instrument
  reads its own current against V / 1 MΩ.
- **L2-3, a real exponential.** An OPX step through the bias tee is captured by the scope. A
  single-exponential fit of the droop gives the bias tee's time constant, which is checked against its
  specification.

## Consequences
- Easier:
  - Nothing to design, build, hand-characterize, version (`dut_golden_v*`) or repair.
  - L2 uses the wiring a real device uses, a bias-teed gate, so it is closer to L3 than the board was.
  - Step 5 needs only two new curated fits: a plane and a single exponential. The diode fit is dropped.
- Harder:
  - No real-hardware test of a nonlinear fit before the fridge.
  - The L2 oracles lean on instrument and bias-tee specifications (input impedance, bias-tee cutoff and
    DC-port resistance) instead of hand-measured parts. A pass threshold is the combined specification,
    computed in the test code (rule 7: no site tolerance written in the repo).
- Must now:
  - Every step file's L2 heading reads "instrument-on-instrument". The plan's §7.1 ladder, the Step 5 file
    and `docs/BENCH.md` say the same. ADR 0004's "maintain the surrogate DUT" and ADR 0007's "build the
    surrogate DUT by Step 5 entry" no longer apply; those ADRs are otherwise unchanged.
  - If a nonlinear real-hardware check is ever wanted, it is one inline part added under a new ADR. A
    board is not brought back by default.

## Alternatives considered
- **Build the surrogate DUT as drafted (PR #24).** Rejected by the human. It is a custom artifact to
  build, characterize and maintain, and what it tests is mostly covered by the instruments themselves
  plus the simulator.
- **A minimal DUT: one inline resistor or diode.** Offered and declined. The scope's 1 MΩ input covers
  the resistive load, and the nonlinear check is the only thing lost.
- **Plain loopback for L2-1, without the bias tee.** Kept only as the fallback if the bias tee is
  unavailable. Each sensed channel would follow one axis, which still catches swapped axes but is weaker
  physics.
