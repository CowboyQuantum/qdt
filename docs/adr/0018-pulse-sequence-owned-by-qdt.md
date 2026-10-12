# 0018 — qdt owns a minimal, backend-neutral `PulseSequence`; backends emit their own ISA; shots and repeats are loops with fixed homes

**Status:** Accepted (amends plan §10 and §4.1)
**Date:** 2026-10-12
**Step:** 2

## Context
ADR 0017 made `SequencerProgram` an envelope around an opaque body, which left the pulse sequence itself
to be authored outside qdt (hand-written QUA, or a generator such as arbok in the internal package). Plan
§10 excluded a "pulse IR/compiler". Two things argued against leaving it there, decided with the human on
2026-10-12:

1. Spin-qubit sweeps execute a full pulse sequence across many gates per pixel, repeated as *shots*, and
   often repeat the whole scan as *averaging*. A sweep that cannot name its per-pixel sequence is not
   "experiments as data"; it is a loop around code someone else wrote.
2. The sequence must be portable across sequencers: the OPX (QUA) now, other AWGs later, including custom
   ones with their own instruction sets. Depending on any one vendor language, or on arbok, to produce the
   per-pixel body ties the public engine to that language.

What stays out of scope is a *general* pulse compiler: arbitrary waveform algebra, phase-tracked frames,
branching and real-time feedback. The OPX constraints measured by Probe 01 (ADR 0015) still apply at the
emitter: integer runtime parameters through scaled input streams, positional results.

## Decision
Add `qdt_schemas.pulse` to the Step 2 slice: `PulseSequence` is an ordered list of per-shot primitives on
logical channels (`step`, `ramp`, `wait`, `drive`, `measure`, `call` of a named `Segment`), with integer
nanosecond timing and `Symbol` placeholders for any level, duration, frequency or amplitude. A
`SweepDefinition` stage takes a `PulseSequence` plus symbol bindings, a shot count and per-result shot
reductions; a per-backend **emitter** translates sequence + stage shape into that backend's
`SequencerProgram` (the ISA-specific body, the scaffold loops, the input streams, the stream processing).
The emitted program is recorded in the `ExecutionPlan`. A raw `SequencerProgram` remains allowed on a
stage as the escape hatch. Plan §10 is amended: a general pulse compiler stays out of scope; this minimal
sequence and its emitters are in.

Loops have fixed homes: **shots** are the innermost loop, run by the sequencer; **repeats** are the
outermost loop, run by the executor, landing in a `repeat` dimension (bounded or unbounded). A reduction
performed by the producer (shots averaged in stream processing) disappears into a parameter and a Dataset
attribute; every other reduction is done by a consumer over a dimension that stays in the data. The
executor never averages.

## Consequences
- Easier: one sequence runs under any sweep that binds its symbols, and on any backend with an emitter;
  segments make "initialise / manipulate / read out" reusable by reference; the simulated backend is just
  the first ISA (qdt-sim interprets the sequence against the dot model, so stability diagrams, line cuts
  and pulsed-gate maps fall out of one interpreter); every pass of an averaged scan stays inspectable for
  drift; the OPX's own averaging and shot reduction are expressible without special cases.
- Harder: qdt owns a pulse vocabulary that grows only by ADR, and the first emitter that needs a primitive
  the vocabulary lacks must add it rather than smuggle it through `attrs`. Emitters must validate timing
  against their clock (4 ns on the OPX) and reject what they cannot express. Keeping shots multiplies data
  volume by the shot count; the stream budget (Analysis 0001) was sized for it. Flight Deck needs a display
  reduction over `repeat` before averaging is visible live.
- Must now: `SweepDefinition`, `ExecutionPlan`, the compiler and executor (`qdt_lab/experiment/`) are built
  around this (ADR 0019 for their shape); the simulated emitter ships in Step 2, the QUA emitter in Step 5
  behind the `[opx]` extra; `DataVariable` has no attrs (frozen), so per-variable reductions are recorded
  in `Dataset.attrs` under `"<variable>.reduced"`.

## Alternatives considered
- Sequence authored outside qdt (arbok or hand-written QUA), qdt sees only the envelope — rejected by the
  human: ties the engine to one language and one internal tool; experiments are not data below the sweep.
- A full pulse IR (waveform algebra, frames, branching) — rejected: plan §10's reason stands; it would be a
  QUA replacement and would not stay portable to simpler ISAs.
- Shots and repeats as free dimensions the user declares anywhere — rejected: their physical meaning is
  their position (innermost: fast noise per pixel; outermost: drift spread over the map), so the schema
  fixes it.
- Running average computed in the executor and re-streamed — rejected: hides passes, makes the executor
  stateful, and duplicates what the consumer can do over a `repeat` dimension.
