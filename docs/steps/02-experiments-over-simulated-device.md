# Step 2 — Experiment formulation over a simulated device

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Experiments are data. A `SweepDefinition` compiles to an execution plan and runs against the capability protocols, with `qdt-sim`'s `SimulatedDevice` as the backend so declared sweeps stream physically meaningful maps into Flight Deck.

## Schema slice
`stand.py`: `InstrumentConfig`, `ChannelMap`, `StandConfig`. `activity.py`: `SweepDefinition`, `ExecutionPlan`. Frozen at exit.

## Deliverables
- `qdt-lab/protocols/`: `LevelSource`, `LevelSense`, `WaveformSource`, `WaveformSense`, `Sequencer` complete (ADR 0016 naming), each with a `Simulated*` twin and the single conformance suite
- `qdt-sim`: `quantum_dot_sim` imported; `DoubleDotValley` exposed as `SimulatedDevice` implementing the protocols
- `qdt-lab/experiment/`: compiler (definition → plan) and executor (plan → protocol calls → `Dataset` stream); backend-payload slot for QUA inner loops
- Flight Deck `live` source

## L0 tests (CI)
- schema validation; dry-run executor produces expected point count, order, shape
- reproducibility: same definition → identical structure and metadata
- charge-stability sweep against `SimulatedDevice` reproduces committed scenario output within tolerance
- conformance suite green on all `Simulated*` backends

## L1 tests (bench loopback)
- none

## L2 tests (surrogate DUT)
- none

## Exit criteria
- a `SweepDefinition` round-trips through serialization and runs on `SimulatedDevice`, live in Flight Deck
- stand + activity slices frozen with ADR

## Open decisions
- QUA payload-slot shape — Probe 01 (ADR 0015): runtime-variable parameters go through an int input stream on one compiled program; fixed-typed input streams do not compile on QOP 3.7.1, so fractional values are scaled ints with the scale recorded

## Status
IN PROGRESS
