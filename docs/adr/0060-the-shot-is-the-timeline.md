# 0060 — The shot is the timeline: a capture is an op of the pulse sequence; no `PlayedWaveform`

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 open decision (amends the pulse slice of ADR 0022 additively; revises a consequence of ADR 0047)

## Context
ADR 0047 put time-resolved capture into the sweep as a per-point activity (`captured`: arm a scope at
every stepped point; the scope triggers itself) and left the stimulus outside: L2-3's OPX pulse train is
played by the bench script beside the sweep, and the record says nothing about what was played. The
Step 6 open decision was named `PlayedWaveform`, a per-point "play a waveform" beside `CapturedWaveform`.

The human saw the seam (2026-10-16): a *shot* exists only inside the sequencer stage, where the pulse
sequence is a timeline of step, ramp, wait, drive and measure. The scope capture was not a shot: it hung
off the point with no relation to that timeline, and a played waveform would have been a third per-point
thing with no relation to it either. In a measurement the shot *is* stimulus plus readout: the sequence
drives the device, and the readout, integrated or time-resolved, is a window on the same timeline,
triggered by it.

## Decision
- **The pulse sequence is the one timeline per shot.** Everything time-resolved hangs off it.
- **Readout is an op in two flavours.** `measure` integrates the sequencer's input, one number per shot
  (unchanged). **`capture`** (new primitive) opens a window on a `WaveformSense` channel at that point of
  the shot: `channel`, `duration` (ns, fixed, never a Symbol), `num` samples, `result`. One record per
  shot, on a time axis that starts at the capture, not at a front-panel trigger. The shot waits for the
  window. A channel is captured once per shot; a capture's result keeps every shot (`reduce` refuses
  `mean`/`sum`: the executor never averages a record, ADR 0018).
- **Stimulus is what the sequence already has.** `step` and `ramp` on a sequencer line are the played
  waveform; the bias-tee step response is `step(rf, 0.1 V, 2 µs); capture(scope1, 8 ms, 200)`. There is
  no `PlayedWaveform` activity and no `play` op: an arbitrary sample array is not in the vocabulary, and
  the Step 6 open decision closes without it.
- **The per-point layer keeps what is per point.** Setting the stepped gates, settling, reading slow
  levels, holding the operating point. `captured` (ADR 0047) stays for what it honestly models: passive
  monitoring on an instrument that triggers itself. A channel is captured in the shot or per point, not
  both.
- **Execution, first slice.** The capture's scope is an instrument of its own (compile refuses a capture
  on the sequencer's own input: "not emitted yet"). The executor arms the scope for one record per shot
  *before* the shots run and re-keys each record to its shot after; the sequencer triggers the capture
  in the shot. A stage with a shot capture has no stage axes (the scope is armed per stepped point;
  step the axis instead), so the sequencer's program may fill nothing at all: it runs its shots and the
  scope records them. On the simulator, the device skips the scope channel (not one of its gates) and
  runs the shots for their clock; the simulated scope records its response as before. The OPX driver
  refuses a shot capture until it emits a trigger line to the scope.
- **Dataset layout.** A shot capture's variable spans the outer dims, the stepped axes, `shot` when
  shots > 1, and its time axis from 0 to `duration`; `time` when every time-resolved variable of the
  sweep shares one grid, else `<result>_time`.
- **Flight Deck.** The pulse editor has a `capture` row (channel, duration, num, result); a stage sweep
  with a capture and no measure is a readout.

## Consequences
- Easier: a record carries its stimulus; a DC × scope-response map is one definition (a stepped axis
  and a shot with a step and a capture); a tune-up node can step a level and record a response; L2-3
  becomes a stage once the OPX trigger line exists.
- Harder: a capture inside the shot needs the sequencer to trigger the scope, which the protocols do not
  express (a marker line in the stand, a trigger op or an implicit one at the capture): the next slice,
  with the OPX driver. Until then the sim is the only backend that runs a shot capture, and L2-3 on the
  bench stays a per-point capture with the pulse train played beside it.
- Harder: a capture on the sequencer's own input (the OPX's ADC, raw acquisition) is the natural second
  slice: then the sequencer fills the trace itself and stage axes can return.
- `reduce: mean` over kept traces is an analysis, not an executor job; a method that averages shots is
  curated like any other.

## Alternatives considered
- `PlayedWaveform` beside `CapturedWaveform` (the open decision as named) — rejected: it would have kept
  stimulus and readout apart from the shot that relates them, and `step`/`ramp` already play.
- A `play` op with explicit samples — deferred: no consumer needs an arbitrary waveform yet; when one
  does, it is a primitive like `drive`, and still an op of the shot.
- A trigger field on `capture` now — deferred: the protocols (ADR 0021) have no marker line; adding one
  is the OPX slice's decision, with a bench to prove it on.
