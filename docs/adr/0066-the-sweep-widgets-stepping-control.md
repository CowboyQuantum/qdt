# 0066 — The Sweep widget's stepping control: one control for the innermost stepped axis, offered when the stand can trigger it; a triggered axis moves the per-point readout into the shot

**Status:** Accepted
**Date:** 2026-10-16
**Step:** follow-up of ADR 0064 (Flight Deck; extends 0054, 0056)

## Context
ADR 0064 gave a stepped axis a `stepping`: `software` (the executor sets and settles each point) or
`triggered` (the axis's DAC is loaded with the levels as a list and advanced by the stage's sequencer, one
point per marker). It also said Flight Deck's Sweep widget did not offer it, and STATUS carried that: a
triggered sweep could only be posted by hand or by a node. The human asked for the control and postponed
the bench work (2026-10-16).

The schema's rules decide the shape of the control: at most one axis is triggered and it is the innermost
stepped one; it needs a stage with a sequence (the sequencer plays the marker); nothing is sensed or captured
per point beside it, because the executor is no longer in the loop per point ("measure or capture in the
shot"). The widget builds three kinds of sweep: a stage sweep (a DC outer axis, a pulsed inner axis, the
Pulse widget's shot per pixel), a DC sweep (two DC axes, the sensor sensed per point) and a capture (an
optional DC axis, a scope record per point).

## Decision
- **One control, below the axes**, named "stepping": "software: set each point" or "triggered by the
  sequencer". It applies to the innermost stepped axis of the kind (a stage or capture sweep's outer axis, a
  DC sweep's inner one) and its hint names that axis and the sequencer. One control rather than one per
  axis row, because only one axis can ever be triggered.
- **Offered only when the stand can do it**, with the reason otherwise (the option is disabled, the hint
  says why). `triggerFor` mirrors the compiler: the channel's instrument loads lists
  (`triggered_level_source`) and is the sequencer itself (the simulated device triggers itself) or names a
  sequencer's channel as `settings.trigger_from` (the marker line). `steppingFor` adds each kind's condition:
  a stage sweep's DAC must be advanced by the sequencer that pulses its inner axis; a DC sweep's sensor must
  be an input of that sequencer; a capture's scope must not be the sequencer's own input (ADR 0060). The
  triggered axis's virtual-gate companions (ADR 0049) are lists too and must follow the same sequencer.
- **A triggered axis moves the per-point readout into the shot**, as ADR 0064 prescribes:
  - *stage sweep*: nothing moves; the pulsed axis and the shots run inside each DAC point.
  - *DC sweep*: the sensed level becomes a one-measure shot on that sequencer: `measure(sensor, integration,
    I_sensor)`, `shots` per point, averaged. The integration (ns) and the shots appear while triggered;
    untriggered, the shots field is hidden (a sensed level has none).
  - *capture*: the per-point capture becomes a capture op in a shot with no pulsed axis, one record per shot
    (`records per point` becomes the shots), starting at its marker: the start is pinned at 0 while
    triggered and restored after. The shot then waits before the next point ("between records", 50 ms by
    default: the bench's value after Probe 05 with segmented memory, ADR 0065; 0 is fine on the simulator).
    This is L2-4's staircase.
- **`software` is never sent**, so a definition without a triggered axis keeps its content hash.
- **The stage builder refuses a capture row while it pulses an axis** (the server's rule, ADR 0060: a shot
  capture's scope is armed per stepped point, so its stage has no pulsed axis). The stage sweep always
  pulses one, so the error now shows while typing instead of at compile, and points at the capture kind,
  whose triggered stepping puts a record in the shot. A capture's result is never in `reduce` (a record is
  kept per shot).
- The next-run line marks the axis "(triggered)" and the plan summary ends "· P2 triggered".

## Consequences
- Easier: the three shapes ADR 0064 named are built from the UI: a fast DC map (outer set per point, inner
  advanced by the sequencer, read in the shot), a lattice-node shape (outer DAC advanced, inner pulsed) and
  the staircase. On the simulator all three run through the server (e2e).
- Harder: a triggered DC sweep reads the sensor through the sequencer's input, not the meter's `LevelSense`:
  on the bench the sensor has to be an OPX input, and the hint says so when it is not. The pacing wait is a
  bench constant a user may have to change with the scope's acquisition mode.
- Not built: a stage with no pulsed axis (a stimulus and a capture or measure per point, L2-3 as one shot).
  The Pulse widget's capture row has no valid stage kind until then; the emitter also refuses a measure with
  no program axis unless shots are kept. That is its own slice.

## Alternatives considered
- A stepping select on every axis row — rejected: at most one axis is triggered; a control on a row that can
  never be triggered is noise.
- Hiding the option when the stand cannot trigger the axis — rejected: a disabled option with its reason
  says what to wire (`trigger_from`, a list-capable DAC), which is what a user at a new stand needs.
- Letting the server refuse — rejected: the builders refuse what the server would, so errors show while
  typing (the Step 4b rule for the form models).
- Moving a capture into the shot without pinning its start — rejected: in the shot a record starts at its
  marker; a negative start would silently shift the time axis.
