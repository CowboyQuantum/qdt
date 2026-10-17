# 0067 — Readout is the sweep's choice: a DC sweep reads its sensor per point or in the shot, a capture records per point or in the shot; the compiler still decides the pacing

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 follow-up (Flight Deck; extends 0060, 0066; takes the builders of #64)

## Context
A triggered axis needs a sequenced stage, and nothing may be sensed or captured per point beside it
(ADR 0064); since ADR 0066 the compiler decides from the stand whether the innermost stepped axis is
triggered. The Sweep widget builds three kinds of sweep, and only the stage kind has a shot, always with a
pulsed axis. From the UI, "auto" could therefore trigger only a stage sweep's outer axis: a fast DC × DC
map and L2-4's staircase could not be built in the widget at all.

A parallel session (#64), written before ADR 0066 merged, built a stepping control that moved a DC sweep's
sensor into a one-measure shot and a capture's record into a shot whenever the user chose a triggered axis,
with the widget mirroring the compiler's wiring rules. ADR 0066 rejected deciding the pacing in the widget,
and #64 also numbered its ADR 0066. The session behind #65 kept #64 out and named its useful remainder: a
readout choice. The human asked to take the readout choices from #64 (2026-10-16).

Two things are separate here. Where the signal is read (by the host at every point, or by a sequencer in
the shot) changes what is measured: a meter's aperture or a sequencer input's integration, a scope armed by
the host or a record from the sequencer's marker. Who paces the DC steps stays the stand's (ADR 0066).

## Decision
Give the DC and capture sweeps a readout choice, per point or in the shot, whose "in the shot" builds the
one-op shot #64 designed on the sequencer that reads it. Leave the pacing to the compiler, so that on a
wired stand "auto" triggers the innermost DC axis once the reading is in the shot.

## Consequences
- Easier: a fast DC map (the inner DC axis triggered, the sensor integrated in the shot, shots averaged) and
  L2-4's staircase (the outer axis triggered, the record captured in the shot from its marker) are built in
  the UI. On the simulated stand both run, and the plan box shows the axis triggered (e2e).
- Easier: the widget checks only what the readout needs. A sensor is read in the shot by the sequencer whose
  input it is (`sensorSequencer`). A capture's shot runs on the sequencer whose marker triggers the scope
  (`settings.trigger_from`, ADR 0063), else on the stand's only sequencer (`captureSequencer`). Otherwise the
  option is disabled and the hint says why. The wiring for pacing stays the compiler's.
- Easier: the stepping preference now applies to the innermost stepped axis of any sweep with a shot (a DC
  sweep's inner axis, else the outer one), not only to a stage sweep's outer axis.
- Harder: read in the shot, the sensor is read by a sequencer input, not by a meter's `LevelSense`. On the
  bench the sensor must be an OPX input, and the widget offers only current channels as sensors, so the
  OPX's voltage input is not offered yet.
- Harder: a DC sweep read in the shot needs its inner axis triggered: its stage has no axis of its own, and a
  host-stepped point would record its measure with no program axis to land on (ADR 0066's rule). The widget
  does not offer "software" then; on an unwired stand the compiler refuses with ADR 0066's message. Lifting
  that rule ("a stage result once per point with no stage axis") would make it portable.
- Harder: in the shot a record starts at its marker, so the capture's start is pinned at 0 while it is
  there and restored after. A wait after each record (default 50 ms) follows the capture; with segmented
  acquisition (ADR 0065) the scope no longer needs it, a settle may.
- Must now: the readout choice is a field of the builders' forms (`readout`, `shot`); per point stays the
  default, so every definition the widget built before keeps its shape and content hash. #64 is closed,
  and nothing of its stepping control or its ADR merges.

## Alternatives considered
- #64 as written — rejected: its widget decided when an axis may be triggered, which ADR 0066 rejected, and
  its ADR took the number 0066.
- The readout implied by the pacing (in the shot whenever the axis would be triggered) — rejected: the widget
  cannot know the pacing before compile, and the readout changes what is measured, so it is the user's choice.
- A new sweep kind per readout — rejected: the same axes and the same form; one control.
- A select for the sequencer that runs the shot — deferred: every stand so far has one sequencer, and the
  scope's trigger line names it when there are more.
