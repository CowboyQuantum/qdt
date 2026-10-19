# 0069 — The sequencer's own input is a sink: a voltage input is a sensor read in the shot, and a capture on it is a program result with its own time axis

**Status:** Accepted
**Date:** 2026-10-19
**Step:** 6 follow-up (extends 0060, 0063, 0067; the bench row L2-5)

## Context
Every sink the bench had proven was the scope: L1, L2-1 to L2-4 and the shot capture of ADR 0063 all
record on the HD3. In the fridge the signal that matters arrives at the OPX's own input, the sensor's
current through a transimpedance amplifier: integrated per shot for a map, recorded over a window for
a time-resolved readout. Two things stood in the way. ADR 0067 noted that the widget offered only
current channels as sensors, so the OPX's voltage input could not be chosen, and that read in the shot
a sensor is a sequencer input, not a meter. ADR 0060 and the compiler refused a capture on the
sequencer's own input ("not emitted yet"), and the Sweep widget's `captureSequencer` repeated the
refusal. The backend already integrated an input in the shot (`measure` on an `ai` port, Probe 02's
constants), untried on hardware with a real signal.

The human chose this slice on 2026-10-19, with a QDAC channel cabled to LF-FEM ai1.

## Decision
- **A sequencer's voltage input is a sensor.** The Sweep and Pulse widgets offer it beside the current
  channels: a voltage channel of a sequencer that sets no level (no `level_source`), is no pulse line
  (the `_pulse` convention) and no marker line (named in some instrument's `settings.trigger_from`).
  It is read in the shot only: per point needs a `LevelSense`, which a sequencer has not; the compiler
  refuses with the capability's name and the widget disables the choice. Its result is `V_sensor`.
  Marker lines are offered nowhere.
- **A capture on the sequencer's own input is the program's result.** The emitter declares a
  constant parameter `n_<result>` (= the capture's `num`) and a result over the program axes, `shots`
  when shots > 1, and `n_<result>`; the channel's role is `sequencer`; the Dataset variable is the same
  (stepped axes, `shot`, time) one a scope's capture gives, declared once; the stage slab carries the
  time dimension; the executor arms nothing and lays the program's frames as it lays any result. On
  the OPX the window is a readout pulse of the window's length (rounded up to the clock) on the input
  element, saving the raw ADC trace per shot, which the host scales by `RAW_ADC_TO_VOLTS` and lays on
  the declared grid from 0 at the capture; the simulated device records its sensor current over the
  window, one sample interval of clock per sample; the simulated sequencer fills the flat index as for
  any result.

## Consequences
- Easier: a DC map read by the OPX's input, the fridge's fast map, is built in the UI and runs
  triggered or stepped from the host (L2-5: slope 0.498 V/V against the 50 Ω-into-50 Ω half, both
  ways). A time-resolved readout on the OPX needs no scope: the staircase recorded on the input gives
  the same plane as L2-4 did on the scope, halved. A stand without a scope captures.
- Easier: no schema changes. `Capture` was already generic ("a WaveformSense channel", the sequencer
  being one), and `SequencerResult.dims` already sizes an axis by a parameter, as ADR 0068's `n_once`
  does.
- Harder: a capture in the shot still needs a stage without stage axes, the schema's rule from
  ADR 0060, written for a scope armed per point. With an own capture a stage axis would be expressible;
  lifting the rule needs the validator to know the stand, so it stands, and the triggered axis is the
  sweep.
- Harder: the widget's classification rests on conventions. A sequencer's output line not named
  `_pulse` is offered as a sensor and refused at compile ("is an ao, not an ai"); a stand that breaks
  the convention gets the server's message, not the widget's.
- Harder: a record stream holds one item per shot, and a result over one program axis arrives when
  the run is done (ADR 0015), so a long staircase recorded on the input fills at once, as a 1-D OPX
  result already does.
- Must now: `_RunSource` and `_DeviceRun` keep `n_<result>` out of the program axes; the stage slab
  includes the capture's time dimension; `MARKER_TO_ANALOG_NS` does not apply to an own capture (no
  marker plays; the record starts at the op after `TIME_OF_FLIGHT_NS`, as Probe 02 set it).

## Alternatives considered
- Arm the OPX's `WaveformSense` for the own capture, as for a scope, and drain it beside the program —
  rejected: one OPX runs one program on its ports at a time, and the record belongs in the shot's
  timeline, where the program's `measure` already puts it.
- A `kind` (input/output) on `ChannelMap` to classify channels — rejected for now: the open decision on
  declaring a sense range is the home for channel metadata, and the two conventions suffice on every
  stand so far; the server stays the authority.
- Keep refusing a capture on the sequencer's input and put a scope on the fridge's readout line —
  rejected: the fridge's readout is the OPX's input, and the scope's segmented path reads 0.30 s per
  record.
