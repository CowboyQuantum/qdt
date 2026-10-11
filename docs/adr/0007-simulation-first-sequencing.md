# 0007 — Simulation-first sequencing; instrument drivers as the last mile

**Status:** Accepted (supersedes the step ordering in 0004; the test ladder in 0004 stands)
**Date:** 2026-10-11
**Step:** all

## Context
ADR 0004 ordered the work instrument-up (drivers first) so every step was bench-testable. On reflection the owner
wants to iterate fast on the interface the lab will actually use and on the data that will stream through it,
and real instrument orchestration is a last-mile concern once the stack above it exists. The architecture already
supports this: rule 8, the `Source` abstraction, `Simulated*` backends behind capability protocols, and `qdt-sim`
exposed as a `SimulatedDevice`. The owner also wants to release up-front requirements pressure and let
architecture evolve through tracked decisions, reserving a deliberate freeze for the two contracts that code
accretes against.

## Decision
Reorder to: 0 bootstrap → 1 `Dataset` contract + Flight Deck v0 (synthetic/replay sources) → 2 experiment
formulation over `SimulatedDevice` → 3 registry → 4 analysis overlays → 5 instrument drivers with L1/L2 →
6 closed-loop tuning → 7 other sources → 8 frameworks. Pull `SimulatedDevice` (DoubleDotValley behind the
protocols) forward from Step 6 to Step 2 so the UI is iterated against real dot physics. Keep the test ladder;
L0 carries the weight until Step 5, when `bench/` reports begin. Requirements are captured as ADRs over time,
except the `Dataset` stream contract (frozen at Step 1) and the capability protocols (frozen at Step 2), which
each get a deliberate freeze with an ADR. Hedge the simulation-first risk with a thin L1 probe in Step 1: a
one-off script that records the real OPX/scope stream envelope, which the synthetic source then emulates.

## Consequences
- Easier: fast UI iteration; the thing streaming in week two is a charge-stability diagram; drivers are added to a stack that already works.
- Harder: instrument reality pushes back late; if it pushes back against the contract, that is expensive — hence the probe.
- Must now: run the L1 probe before freezing the contract; keep `Simulated*` backends honest (conformance suite is the spec); build the surrogate DUT by Step 5 entry.

## Alternatives considered
- Keep 0004's instrument-up order — rejected: slow UI iteration, drivers built before the data model they feed is known.
- Pure simulation-first with no probe — rejected: contract frozen against assumptions about chunk rates and QUA constraints.
