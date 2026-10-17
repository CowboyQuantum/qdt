# 0066 — Pacing is the plan's: the compiler decides from the stand how each axis advances; `SweepAxis.stepping` is a preference defaulting to "auto"

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 open decision (partly supersedes 0064; extends 0019, 0063)

## Context
ADR 0064 put the choice between host stepping and a triggered DAC list on the axis, inside the sweep
definition, defaulting to software. The human asked (2026-10-16) whether the Sweep widget was the
right place for that control, and whether a software sweep and a hardware sweep deserved a formal
place in the code. Two different decisions had been bundled under that name:

- **What produces the level.** A DC source holds it, or the sequencer plays it as a pulse inside the
  shot. These differ physically: another line, another bandwidth, and a pulse adds on the DC level.
  The choice is already formal, because it is the axis's channel (`P2` or `P2_pulse`). It belongs to
  the experiment.
- **Who paces the DC steps.** The host sets each level over SCPI, or the sequencer's marker advances
  a loaded list. Both give the same levels on the same line and the same Dataset; only the timing
  differs. It belongs to the stand's wiring.

ADR 0063, written the same day, kept the scope's trigger line out of the definition on exactly that
ground; 0064 did the opposite for the DAC. With the choice in the definition, a definition marked
"triggered" does not compile on a stand without the cable, and every author of a sweep (the widget,
the tuning nodes, a script) has to know the wiring to get the fast path. The compiler already resolves
a definition against a stand (ADR 0019), and the registry stores the plan it produces (ADR 0025).

## Decision
Let the compiler decide from the stand how each axis advances and record the decision in the plan and
the Dataset, keeping `SweepAxis.stepping` only as a preference whose default, "auto", triggers the
innermost stepped axis wherever the stand wires it to the stage's sequencer and the sweep allows it.
Show the decision in the Sweep widget rather than asking for it there.

## Consequences
- Easier: one definition runs on any stand. On the bench the QDAC axis is triggered from `do2`; on
  a stand without the cable it is stepped from the host; on the simulated device, its own sequencer,
  it is triggered with no line. The tuning nodes get the fast path with no change.
- Easier: every record says how it was taken. `ExecutionPlan.pacing` holds one `AxisPacing` per axis
  (`software`, `triggered` with its marker lines, or `sequencer`), and the Dataset's attrs carry
  `<axis>.pacing`.
- Easier: the Sweep widget needs no wiring knowledge. Its plan box shows "P1: triggered on
  dac_trigger" or "P2: swept in the sequence"; an "outer stepping" select (auto, software, triggered)
  is the override for a stage sweep.
- Harder: a definition's timing now depends on the stand. Host stepping added an OPX job submission
  per point, which may have hidden a settle that is too short in a stand file; triggered, exactly the
  declared settle is waited.
- Harder: on the OPX a triggered run's results arrive when the program ends, because the driver
  fetches once, so a stability diagram's live view fills at the end instead of row by row. "software"
  is the override until the driver streams per row.
- Harder: a stage with no axis of its own and one shot records a once-per-point result only where the
  program owns the axis. Triggered it compiles; host-stepped it meets the older rule that a stage
  result needs an axis or kept shots. The compiler now says so and names the remedies.
- Harder: changing the default reinterprets stored definitions without `stepping` from "software" to
  "auto". Accepted: pacing was not part of what a definition meant before ADR 0064, a day earlier;
  nothing stored forces either value; and the stored plans still record how the old runs went.
- Must now: `qdt_lab.experiment.resolve_pacing(definition, stand)` decides. The innermost stepped axis
  is triggered when its preference is "auto" or "triggered", the stage has a sequence, nothing is
  sensed or captured per point, and the axis and every coupled companion sit on
  `triggered_level_source` instruments wired to the stage's sequencer by `settings["trigger_from"]`,
  or on the sequencer itself. Every other stepped axis is stepped from the host; stage axes are
  "sequencer".
- Must now: "triggered" is required, so a stand that cannot honour it is a compile error; "software"
  forces host stepping; a stage axis accepts only "auto". A `trigger_from` naming no channel of the
  sequencer is an error even on "auto": a stand file mistake never becomes a silent fallback.
- Must now: the executor reads the plan (`triggered_axis`, `program_axes`, `software_axes`), never the
  definition. A plan compiled before this ADR has no pacing and reads as stage axes in the sequencer
  and every other axis stepped from the host. An empty `pacing` and an "auto" `stepping` are left out
  of serialization, so stored content hashes keep.

## Alternatives considered
- Keep the choice in the definition, as ADR 0064 wrote it — rejected: wiring is the stand's (ADR 0063);
  definitions stop being portable, and every author must know where the cables go.
- Two kinds of sweep, software and hardware — rejected: one measurement mixes them (host-stepped outer
  axes, a triggered inner DC axis, a pulse amplitude in the shot), and one definition, one plan and one
  record kind stay, as ADR 0047 argued for captures.
- Decide in the Sweep widget from the stand — rejected: the tuning nodes and scripts build definitions
  too; the decision would be made in three places.
- "auto" with no override — rejected: debugging, a misbehaving list, or a filtered line whose settle is
  not yet known want host stepping on a wired stand; and a required trigger turns a missing cable into a
  compile error instead of a silent slowdown.
- Derive `SequencerStage.axes` from the channels too — deferred: the plan's validator checks that the
  stage axes are exactly the sequencer-paced ones; removing the field is a migration of stored
  definitions for no new capability.
