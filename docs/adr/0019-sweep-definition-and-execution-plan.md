# 0019 — `SweepDefinition` and `ExecutionPlan`: axes bind symbols, the stage owns the innermost axes, the plan is structural, the executor is stateless

**Status:** Accepted
**Date:** 2026-10-12
**Step:** 2

## Context
Step 2 needs "experiments as data": a `SweepDefinition` that compiles to an `ExecutionPlan` and runs
against the capability protocols (ADR 0016/0017), with the per-shot `PulseSequence` as a parameter
(ADR 0018). The one experiment that must run live at Step 2 exit is a charge-stability diagram: outer
gate stepped by a level source, inner gate swept by a sequencer program, shots per pixel, optional
repeats of the whole scan. Four choices were put to the human on 2026-10-12 and accepted: parameter
bindings by axis property, the stage consumes the innermost axes and the executor offsets its frames,
a structural plan rather than an unrolled op list, and scope captures per point deferred.

## Decision
`SweepDefinition` = ordered `axes` (name, logical channel, start, stop, num), `sensed` levels read at
every stepped point, an optional `stage` (sequencer instrument, the innermost axes it sweeps, a
`PulseSequence` with one `SymbolBinding` per symbol to an axis or a constant, or a raw program bound
through `ParameterBinding`s, `shots`, per-result `reduce`), and `repeats` (int or None = unbounded).
`compile_sweep(definition, stand, emitters)` resolves every logical channel to one role (`ResolvedChannel`),
checks capabilities, has the backend's `Emitter` produce the stage's `SequencerProgram` and
`ParameterBinding`s (const / axis_num / axis_start / axis_step / axis_value, through each parameter's
scale), and declares the `Dataset`: `repeat` outermost when repeats ≠ 1, one dim + `LinearCoordinate` per
axis, `shot` innermost when shots are kept, sensed variables over the stepped axes, stage results over all
axes. `ExecutionPlan` holds all of that and nothing unrolled. `Executor(plan, backends)` walks it: repeats →
stepped axes row-major (set changed levels, sleep the longest settle among them, sense) → one sequencer
run per stepped point against an inner "slab" Dataset, whose frames are re-keyed with the outer index
slices and renumbered. Sensed levels are chunked one innermost line per frame. The returned `Source`
marks the last frame `final` when bounded.

## Consequences
- Easier: one definition runs stepped-only (QDAC + SMU loopback, Step 5) or staged (OPX) with no change
  in shape; a symbol bound to a *stepped* axis becomes a per-run `axis_value` parameter, so the sequencer
  can pulse the outer gate to its current value; the plan is small, serializable and the exact record of
  what ran (Step 3 provenance); the dry-run tests (count, order, shape) walk the same code the live run
  does; a stand of only `simulated` backends yields `SourceDescriptor(kind="simulation")`.
- Harder: every chunk is a hyperrectangle of one repeat × one outer point × a whole inner line, so a
  stage with one axis streams one frame per stepped point (fine at Analysis 0001 rates); the sequencer
  is handed the slab, not the full Dataset, so a driver that wants the outer index must read it from the
  parameters; a sensed level with no stepped axis is only legal with repeats ≠ 1 (it needs a dimension).
  `axis_value` may not name a stage axis.
- Must now: the executor's one-terminal-one-role check is at compile time (ADR 0016); `settle_s` is
  honoured by the executor; `integration_s` by the driver. `qdt-sim`'s `SimulatedDevice` implements
  `Sequencer` for backend `simulated` by interpreting the emitted body (sequence JSON + symbol map)
  against the dot model. Scope captures per stepped point (`WaveformSense`) are a later slice, same shape
  as `sensed` with a time axis.

## Alternatives considered
- Unrolled `ExecutionPlan` (one op per set/sense/run) — rejected: a 2048² sweep is millions of objects;
  the structure is the plan, the walk is code.
- Sequencer runs the whole map (outer axis inside the program) — rejected as the only mode: the outer
  gate is usually a DC source the sequencer cannot drive; kept as a special case (no stepped axes).
- Executor builds one full Dataset and re-labels sequencer output — rejected (ADR 0017): the slab is one
  line of code and keeps the sequencer honest about the grid it fills.
- Settle as a per-point sleep of the sum of channel settles — rejected: channels settle concurrently;
  the longest among the *changed* ones is the wait.
- Scope captures in this slice — deferred: nothing before Step 5 reads a scope per point.
