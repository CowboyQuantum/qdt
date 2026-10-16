# 0063 — The shot capture runs on the OPX: the scope triggers itself until it has a marker line; a digital output is a marker line a stand wires to a trigger input

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 open decision (closes the "sequencer-to-scope trigger line" of ADR 0060; extends 0047)

## Context
ADR 0060 made `capture` an op of the shot and left the OPX driver refusing it "until it emits a
trigger line to the scope". The human asked (2026-10-16) whether an edge trigger on the signal is not
enough. For L2-3 it is, and that is why the per-point form has passed since 2026-10-15. It is not
enough in general: with a self-triggered scope t = 0 is wherever the signal crossed the level (it
drifts with amplitude on a slow response), a shot with several edges fires on the first, a capture on
a baseline or a small slow response has nothing to trigger on, and a missed or spurious trigger
silently shifts every later record onto the wrong shot. The human chose both: the shot definition now,
with the scope triggering itself, and the marker line as a setting on the same path.

Two things no emulator can tell: the marker's level and its delay to the analog edge, and how fast the
scope re-arms between records. Probe 05 measures them; until it has run, the self-trigger interim is
the honest form on the bench.

## Decision
- **A digital output is a channel of the OPX**: `do<p>` / `fem<f>/do<p>`, declared in the stand as a
  `voltage` channel like any other, and used only as a marker line. The driver's config gives it a
  digital-only element with one `marker` pulse of `MARKER_NS` (400 ns, a value Probe 05 confirms or
  changes). Markers play on their own element, so the analog timeline is not delayed by them.
- **The stand wires a line to a trigger input on the receiving instrument's side**: that instrument's
  `settings["trigger_from"]` names the logical marker channel. The compiler resolves it (the line
  must be a channel of the stage's sequencer), hands the emitter `lines` (capture channel → line) and
  the OPX driver plays the marker on that line at the capture op. The scope driver, built with
  `trigger_from`, sets its trigger at `arm`: EXT TRIG, rising edge at `settings["trigger_level_v"]`
  (default 1.0 V), NORMal sweep. Everything else on the scope stays the user's (ADR 0047).
- **Without a line the scope triggers itself** (the interim): the OPX driver compiles the capture as a
  wait of the window's length and plays no marker; the scope's trigger is whatever the front panel
  says. Documented limits: one clean edge per shot, t = 0 is that edge, not the op; a record is
  keyed to its shot by order alone. `qdt-server --stand` without `trigger_from` on the scope runs this
  form today.
- **The executor drains a shot capture on a thread.** A real scope acquires only while its records
  are being read (`:DIGitize` per record), which the simulator never showed: the executor now starts
  reading each armed capture's frames before it starts the sequencer, waits `CAPTURE_ARM_GRACE_S`
  (50 ms) for the arm to land, and yields the records after the shots. An error in the drain is
  re-raised in the executor. The scope's VISA timeout (10 s) bounds a capture that never triggers.
- **A shot capture's sequence paces itself.** The scope re-arms between records through SCPI; a shot
  that fires faster than that loses records (the drain then times out rather than mis-keying). Until
  Probe 05 says what the floor is, a shot capture's sequence ends in a `wait` of a few hundred ms.
  Segmented acquisition (arm once, catch every trigger in hardware) is the follow-on if the HD3
  accepts it; Probe 05 asks.
- **The capture window is rounded up to the OPX clock** in the driver; the window itself is the
  scope's grid.

## Consequences
- Easier: L2-3 is a one-shot definition (`bench/test_l2_paced.py`): `step(P2_pulse, 0.25 V, 16 ns);
  capture(scope1, 29 µs, 2900)`, with the scope self-triggering on the analog edge as before; the
  same fit, the same oracle. A tune-up node can step a level and record a scope response.
- Easier: the marker is a stand setting, not a sweep setting: a stand that has the cable turns it on.
- Harder: with the marker, the record starts at the capture op, which sits after the stimulus op in
  the shot: a `step` of 16 ns then a capture misses the first 16 ns plus the marker-to-analog delay
  Probe 05 measures. A capture *before* the stimulus (a pre-trigger baseline) is a scope ability the
  shot does not express; the self-trigger form sees the edge at t = 0 because the scope found it.
- Harder: per-record `:DIGitize` bounds the shot rate; segmented memory is the next scope slice.
- Must now: run Probe 05 (`docs/probes/05-sequencer-trigger-lines.md`); set `trigger_level_v` and
  `MARKER_NS` from it; add the EXT cable and `trigger_from` to the bench's stand file.

## Alternatives considered
- Keep refusing until the marker exists — rejected by the human: the shot definition is wanted now.
- A `trigger` op in the pulse vocabulary — rejected: the capture implies its trigger; a visible op
  would let a sequence trigger a scope it does not capture.
- A `trigger` field on `Capture` naming the line — rejected: the wiring is the stand's, not the
  sweep's; the same definition runs on a stand with or without the cable.
- Driving the scope's trigger from the OPX's analog output through a splitter — rejected: it ties
  the trigger to one stimulus channel and halves the signal into 50 Ω.
