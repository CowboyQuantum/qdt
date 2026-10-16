# 0064 — The sequencer paces the bench: a `TriggeredLevelSource` beside the frozen five, a stepped axis advanced by the sequencer's marker (`SweepAxis.stepping = "triggered"`), the QDAC-II list mode

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 open decision (closes "sub-ms stepping"; adds a protocol beside ADR 0021's five; extends 0019, 0049)

## Context
A stepped axis is set by the executor: `LevelSource.set`, a sleep of `settle_s`, then the stage
(ADR 0019). Probe 04 put the floor of that at the serial command path (under 4.5 ms, steady to
0.2 ms) while the QDAC-II's output settles in microseconds, and left the Step 6 decision: faster
stepping has to move the step onto the sequencer. The human decided (2026-10-16): the DC source is
what a sweep steps by default; the sequencer sweeps only a pulse amplitude inside a shot; and the DC
step should be able to advance on a trigger line from the sequencer, so the sequencer paces the whole
measurement. The OPX's digital outputs are marker lines (ADR 0063); the QDAC-II has a list mode per
channel that advances one point per trigger on a rear input.

`LevelSource` (`set`, `get`) cannot express "load this list, advance on a trigger". The five
protocols are frozen (ADR 0021); a new ability is an ADR beside them, not an edit.

## Decision
- **`TriggeredLevelSource`**, a sixth protocol, a `LevelSource` that also has `load(channel,
  values)` (load and arm: the output moves to `values[0]` on the first trigger, one point further on
  each later one, and holds after the last), `advance(channel)` (the trigger fired from the host: the
  conformance suite's way, and a ValueError on an input the host cannot fire) and `release(channel)`
  (leave the list, hold the present level; `set` applies again). Capability key
  `triggered_level_source`. The trigger input is the instrument's business: `settings["trigger_in"]`
  on the QDAC-II (`ext1`..`ext4`, or `bus` by default, fired by `*TRG`).
- **`SweepAxis.stepping`**: `"software"` (the default, not serialized, so content hashes keep) or
  `"triggered"`. A triggered axis is the innermost stepped axis, at most one, on an instrument with
  the capability; it needs a stage with a sequence (the sequencer plays the markers) and allows
  nothing sensed or captured per point (the executor is not in the loop per point; measure or capture
  in the shot). Its couplings (ADR 0049) are loaded as lists too, from their held levels.
- **The program owns the axis.** The emitter treats the triggered axis as the outermost program axis:
  `n_<axis>`, symbols bound to it as `<sym>_start`/`<sym>_step`, results laid over it; the body
  carries `triggered` (axis, marker lines, settle in ns). The OPX program's outer loop plays a marker
  on each line, waits the channel's settle, aligns, then runs the inner loops and shots. The
  simulated device, its own sequencer, needs no line: each loaded list sits on the program's point.
- **The executor** loads the lists before every program run (so each run starts at the first point),
  arms a shot capture's scope for points × shots records and re-keys record → (point, shot), and
  releases the lists when the plan ends. The last point holds (ADR 0038).
- **The wiring is in the stand**: the stepped instrument's `settings["trigger_from"]` names the
  sequencer's marker channel (as for a scope, ADR 0063); the compiler resolves it as a sequencer
  channel. A `trigger_from` that is not the sequencer's channel, or a missing one on an instrument
  that is not the sequencer, is a compile error.
- **QDAC-II**: `sour<n>:dc:volt:mode list`, `list:volt`, `list:tmod step`, `list:coun 1`,
  `list:dir up`, `dc:trig:sour <trigger_in>`, `dc:init`; `dc:abor` then `mode fix` and the held
  level on release; `get` in list mode reports the point the driver believes played. The emulator
  understands exactly these and advances on `trigger(source)`. The commands are the manual's; Probe
  05 confirms them, whether `init` moves the output before the first trigger, the trigger-to-output
  latency and the settle per step.

## Consequences
- Easier: a stability diagram's inner DC axis runs inside one OPX program with the QDAC advancing on
  the OPX's clock; the per-point SCPI write and sleep are gone. The lattice nodes' two plunger axes
  can be one triggered DC axis and one pulse-amplitude stage axis.
- Easier: the Dataset is unchanged (the axis was a stepped axis and still is); Flight Deck and the
  registry see nothing new. Flight Deck's Sweep widget does not offer the stepping yet (a follow-up).
- Harder: a triggered step is only as fast as what it drives: direct into 1 MΩ the QDAC settles in
  under a millisecond (Probe 04); through the combiner's DC side the 20 Hz low-pass still sets 50 ms.
  The settle travels into the program from `ChannelMap.settle_s` and is waited on the OPX.
- Harder: a program run covers the whole triggered axis, so a scope capturing per shot is armed for
  points × shots records and the shot must pace itself (ADR 0063).
- Harder: the SCPI list syntax and the first-trigger behaviour are from the manual until Probe 05
  runs; a wrong guess is a one-line driver change the probe reports.
- Must now: Probe 05 on the bench; the L2-4 staircase row (`bench/test_l2_paced.py`): QDAC ch01
  listed over five levels, advanced by do2 → ext1, each point captured on the scope (do1 → EXT),
  plateau against the level, records against points.

## Alternatives considered
- Editing `LevelSource` with the three methods — rejected: the five are frozen (ADR 0021); a sixth
  protocol beside them is the rule.
- The OPX's own analog output as the fast DC step (an offset per point, as the Step 6 file named) —
  rejected for the default: the human wants the DC source stepped by default, the OPX only for a
  pulse amplitude inside a shot; the OPX's ±0.5 V direct range is also not a gate's range.
- A QDAC list on its internal dwell timer (`tmod auto`) with no trigger — rejected: nothing then
  relates the DAC's clock to the shot's; the marker is the relation.
- A `trigger` op the sequence places itself — rejected (as in ADR 0063): the advance belongs at the
  top of the axis's loop, which the program owns; a sequence that triggered its own DAC mid-shot would
  break the axis.
- Several triggered axes (nested lists on several inputs) — deferred: one line, one list; an outer
  software-stepped axis covers the rest.
