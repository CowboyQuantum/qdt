# 0020 — `qdt-sim` written fresh: constant-interaction double dot, periodic charge sensor, clocked noise models

**Status:** Accepted (amends plan §2: `qdt-sim` is not imported from `quantum_dot_sim`)
**Date:** 2026-10-12
**Step:** 2

## Context
Plan §2 and the Step 2 file said `qdt-sim` would import `quantum_dot_sim` and expose `DoubleDotValley`
as `SimulatedDevice`. No such package exists in the workspace or the lockfile, and the human chose on
2026-10-12 to write the model fresh and to include noise, so simulated data looks like data: drifting
honeycombs, sensor jumps, shot scatter. `SimulatedDevice` must stand behind the frozen-at-exit protocols
(ADR 0016/0017) and interpret the body `SimulatedEmitter` produces (ADR 0018/0019), so that every sweep
Step 2 declares runs on physics with no code path that only exists for the simulator.

## Decision
`qdt-sim` ships three layers. `DoubleDotModel`: constant-interaction electrostatics on two dots
(`c_dot`, `c_gate` with cross-capacitance, Boltzmann occupation at an electron temperature over an integer
window) and an SET-like sensor (lever arms, per-electron shifts, periodic thermally broadened Coulomb peaks),
a pure function of gate voltages. `noise.py`: seeded, clocked processes (`WhiteNoise`, `TelegraphNoise`
with an exact two-state propagator, `OneOverFNoise` as an ensemble of log-uniform-rate fluctuators,
`Composite`). `SimulatedDevice`: one object implementing `LevelSource`, `LevelSense` and `Sequencer` on
vendor channels with roles (a gate name, or `sensor`); several channels on one gate add (bias-tee
semantics: pulses ride on the DC level); a device clock advanced by integrations and pulse durations on
which noise is sampled; each shot samples the Boltzmann charge state (or uses its mean); `compile` accepts
backend `simulated` only and interprets the sequence quasi-statically at every `measure`. Scenarios
(`scenarios.py`) and a committed 24×32 fixture pin the behaviour; `python -m qdt_sim` streams a stability
diagram live.

## Consequences
- Easier: a declared sweep (tutorial 01's shape) runs on physics with zero simulator-specific schema;
  the executor's oracle test is the model itself (no noise, mean occupation: the sweep equals the model
  on the grid); shots, reductions and repeats all carry real signal (shot scatter from charge sampling and
  readout noise; pass-to-pass drift from 1/f); the fixture test catches any physics regression at 1e-9.
- Harder: no tunnel coupling, no spin, no valley, no Pauli blockade, no time-domain response inside a
  pulse (durations only advance the clock). Each is an ADR when a sweep first needs it. The per-shot
  Python loop is fine for 10⁴–10⁵ pixels; vectorise before using it as a throughput source.
- Must now: plan §2 and the Step 2 file say "written fresh"; the fixture is regenerated only with the
  model (`scripts/make_sim_fixtures.py`); `qdt-sim` depends on `qdt-lab` (protocols, `Frame`), never the
  reverse.

## Alternatives considered
- Import `quantum_dot_sim` — rejected: not available; owning the model keeps the simulator honest with
  the protocols and the emitter body.
- Hubbard / tunnel-coupled model from the start — rejected: the honeycomb and the sensor are what Step 2
  needs; coupling is a parameter to add, not a rewrite.
- Noise as post-hoc additive Gaussian on the map — rejected by the human's ask: real artefacts are
  correlated in time (drift, telegraph jumps) and in the charge state (shot statistics).
- Fixed-Δt noise integration — rejected: the exact two-state propagator needs no step and is correct for
  the irregular times a sweep produces.
