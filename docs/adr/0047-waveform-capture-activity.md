# 0047 — Waveform capture as an activity: `CapturedWaveform` in the sweep, a `(record, time)` slab per stepped point, a simulated scope on the server's stand, traces drawn as traces

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 5 (amends the activity slice frozen by ADR 0022, additively; the control path of ADR 0032)

## Context
L2-3 (BENCH.md, ADR 0040) captures a network's step response on the scope and fits a single exponential
(ADR 0046). With the scope as L2-1's sink (human decision, 2026-10-15), L2-1's plane also comes out of
a scope record. Neither could come through the control path: `SweepDefinition` knew stepped axes,
sensed levels, an operating point and a sequencer stage; `compile_sweep` never armed a `WaveformSense`;
the executor's role table had no entry for it. Probe 02 and Probe 03 built their scope Datasets by hand
and called `arm` directly, which is fine for a probe and not for a feature the human wants in the web
app: a capture that streams live, is recorded in the registry and can be analysed from Flight Deck
like any sweep. The human asked for the capability in the server rather than a bench-only shortcut.

Three forces shaped the design:
- **A `WaveformSense` fills `(record, time)`** (ADR 0017, 0021): it is handed a Dataset with a record
  dim and a `LinearCoordinate` on time and returns one whole record per frame. The sweep's Dataset has
  more dims (repeat, stepped axes), so the executor must hand the backend a slab and re-key its frames,
  as it does for stage frames.
- **Additive schema changes are accepted without a version bump** when nothing stored changes meaning
  (ADR 0037, 0038); the slice is frozen by ADR 0022.
- **Flight Deck chooses its view from the Dataset's shape** (rule 8). A stored scope record has a sized
  record dim and would have rendered as a records × time heatmap; and a trace shown after a heatmap on
  the same page drew nothing, because the map renderer's WebGL context on the plot canvas refuses the
  2-D context the trace renderer asks for (a latent bug the capture e2e test found).

## Decision
- `SweepDefinition.captured: tuple[CapturedWaveform, ...]` (name, channel, `start_s`, `stop_s`, `num`,
  `records`), excluded from serialization when empty so existing definitions keep their content hash.
  A sweep may capture alone (no axis, no stage, no sensed level). Captured channels are neither stepped
  nor sensed nor held; a channel is captured once; every capture of a sweep takes the same `records`.
- Dataset layout (compile): the capture's variable spans the outer dims, the stepped axes, `record`
  (only when `records > 1`) and a time axis in seconds, named `time` when every capture of the sweep
  declares the same grid and `<name>_time` otherwise. `record` and `time` join `repeat` and `shot` as
  reserved names. Compile resolves the channel as `waveform_sense`.
- Execution order per stepped point: set and settle, the stage, the sensed levels, then each capture in
  turn: a `(record, time)` slab Dataset is built from the plan, the backend's `arm` returns its source,
  and every frame is re-keyed with the point's prefix (the record slice dropped when there is no record
  dim). Captures of one point are sequential, not simultaneous.
- The server's simulated stand gains a `WaveformSense` instrument, `scope`, with one channel `scope1`;
  `simulated_backends` builds a `SimulatedWaveformSense` whose record is a bias tee's droop
  (`exponential_decay`: a step of `droop_v` at t = 0 decaying with `tau_s`), under `scope_noise_v` of
  noise; the three are run options. `SimulatedWaveformSense` takes a `response(times)` callable
  (default: the ring-down it always produced; `low_pass_step` models Probe 03's combiner).
- Flight Deck: a third sweep kind, *capture*, in the control panel (channel, window, samples, records,
  variable; the outer axis optional); `standChannels` classes a channel on a capture-only instrument as a
  waveform, not a DC line; `chooseView` shows a 2-D variable whose leading dim carries no coordinate over
  one that does as a trace of the latest record, sized or not (two coordinated dims stay a heatmap, so a
  DC × time map is one); traces draw on the 2-D overlay canvas with the map canvas hidden, and draw every
  1-coordinate `marker` on their x axis as a labelled rule (the exponential's edge and τ).

## Consequences
- Easier: L2-3 and the restated L2-1 run through `qdt-server --stand` like any sweep: definition → the
  scope → the stream → the registry → the fit from Flight Deck. The L0 model of L2-3 is an API test:
  a capture on the simulated scope, recorded, τ recovered by the exponential within 2 %. The bench
  tests need no Dataset construction of their own.
- Easier: a capture at every point of a stepped DC axis is one definition, so a DC × time map (the
  combiner's response at each level) is a heatmap in Flight Deck with no new renderer.
- Easier: the simulated stand now has the bench's shape in software, so a stand file's capture section
  can be rehearsed off the bench; and the blank-trace-after-heatmap bug is fixed.
- Harder: a capture's trigger is the instrument's own (the scope's front-panel or driver trigger), not
  something the sweep expresses; and nothing in the sweep plays the pulse the capture records. L2-3's
  bench test plays its OPX pulse train through `WaveformSource.play` beside the sweep, as Probe 03 did.
  A `PlayedWaveform` activity (play a waveform at every point) is a later addition in the same shape.
- Harder: captures of one point are armed one after another; two scope channels that must be captured
  on the same trigger need a multi-variable `arm`, which the frozen protocol (ADR 0021) does not have.
  One channel per capture for now.
- Harder: a 3-D capture variable (stepped axis, record, time) has no v0 view yet; Flight Deck says so.
  Records > 1 with a stepped axis is for the registry and the analysis, not for the live view.
- Harder: Flight Deck still offers every method on every record (`applies_to` not read); the time-series
  view's remaining work is that filter, axes and labels on the trace, and an output curve beside it.
- Must now: a stand file for L2-3 lists the scope with `waveform_sense` and a `scope1`-style channel; a
  bench session writes the L2-3 test as a capture definition through the server; `docs/BENCH.md`
  records the trigger convention.

## Alternatives considered
- Keep captures out of the sweep and let the bench test call `arm` (Probe 03's way) — rejected by the
  human: the feature is wanted in the web app, and a record that never passes the registry is not a
  Step 5 exit run.
- A separate `CaptureDefinition` and a second API route — rejected: a capture at every point of a
  stepped axis is a sweep; one definition, one plan, one run lifecycle, one record kind.
- Captures as a `SensedLevel` variant (a "level" that is an array) — rejected: a sensed level is laid
  over the stepped axes only and chunked per line; a capture has its own dims and its own producer
  protocol with its own frame cadence.
- One time dimension for every capture regardless of grid — rejected: two captures with different
  windows cannot share a `LinearCoordinate`; per-capture `<name>_time` always was the alternative, and
  the shared `time` for the common case keeps two channels on one scope subtractable in the view
  (ADR 0037's "minus").
- Making the `SimulatedDevice` (the double dot) a `WaveformSense` too — rejected: the dot model has no
  time-domain output, and a separate simulated scope mirrors the bench's instrument list.
- Drawing the trace on the map canvas by tearing down the WebGL renderer — rejected: recreating a
  renderer per view switch costs context setup and the overlay canvas is already the 2-D surface.
