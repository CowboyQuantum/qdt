# 0046 — The curated single exponential: an edge-anchored window, nonlinear least squares with standard errors, markers on the time axis; `applies_to` gains `trace_1d`

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 5 (amends the control slice frozen by ADR 0036, additively)

## Context
L2-3 (BENCH.md, ADR 0040) steps a pulse source into a passive network and reads the output on the
scope: a bias tee's droop decays to zero with the low-frequency time constant of its datasheet; Probe
03's combiner, which stands in for it on the bench, approaches a step's plateau with τ = 7.9 ms on its DC
side. The step asked for a single-exponential fit as a curated `qdt-analysis` method (Step 5
deliverables; ADR 0041: "drivers first, simple; fits later"). Probe 03's step records are its first
real inputs, and the probe script carries its own 10–90 % log-linear fit that this method replaces.

Three things differ from the methods so far (ADR 0029, 0030, 0045):
- **The data is a trace, not a map.** A `WaveformSense` fills `(record, t)`: time on a
  `LinearCoordinate`, records uncoordinated. `MethodSpec.applies_to` admits only `map_2d`, and Flight
  Deck has no time-series view yet (tabled 2026-10-14).
- **The model has a start.** `offset + amplitude · exp(−(t − t₀)/τ)` is only an exponential after the
  edge; points before it break the fit, and `t₀` is degenerate with `amplitude`, so it must be fixed,
  not fitted. A scope's trigger does not give it (Probe 03 triggered at half the step).
- **An overlay on a trace needs the value axis.** `Annotation.coords` are coordinate names, and the
  value is a data variable, so a fitted curve cannot be drawn as an annotation on the record's Dataset.

## Decision
`qdt_analysis.exponential.fit_exponential` fits `y = offset + amplitude · exp(−(t − t_start)/tau)` by
nonlinear least squares over a window anchored on a detected edge: the edge is the centre of the
strongest part of the *first* run where the box-smoothed slope (width `n // 100` samples) reaches half
its maximum; the window starts at the first sample after it plus `skip` and lasts `span` (0: to the end
of the record); `amplitude` is the exponential term at the window's first sample, `t_start`. It reports
`tau`, `amplitude`, `offset` with standard errors from the residual variance, `residual_rms` and `r2`;
it fails on a trace with no edge, fewer than four points after it, a constant window, a fit that does not
converge, or an exponential explaining less than `min_r2` (default 0.5) of the window's variance; its
overlays are two `marker` annotations on the time coordinate, the edge (`t_start`) and `t_start + tau`;
its output payload is the fitted curve and the residual over the record's time coordinate, NaN outside
the window. It refuses a variable with a coordinate on a leading dim (a map). It is in
`qdt_server.catalogue` as version 1 with `applies_to = "trace_1d"`, a value added to the frozen
`MethodSpec.applies_to` literal without a version bump, as ADR 0037 did for the pulse slice.

## Consequences
- Easier: L2-3's pass criterion is `tau` and its `stderr` against the network's specification, with
  no fitting code in the bench test. The real combiner step (Probe 03's fixture) is an L0 test:
  τ = 8.1 ms by this method against 7.9 ms by the probe's 10–90 % fit, within the 5 % the test allows;
  the two are different estimators of a record whose onset is slow and noisy.
- Easier: the first-run rule picks a pulse's rising edge over its falling one, so a droop fit needs only
  `span` to keep the falling edge out; the centre-of-the-strongest-part rule puts a sharp edge on its
  sample and a slow onset late rather than early, which is the safe side.
- Harder: the edge detector is a heuristic with a fixed smoothing width, not a parameter. A trace with
  a glitch steeper than its edge, or a record whose edge sits in the last three samples, fails; the
  user then clips the record or sets `skip`. A change to the detector is a `VERSION` bump.
- Harder: a single exponential on a multi-exponential droop (the combiner's pulse side, time constants
  from µs to 100s of µs) fits the fastest component with a high `r2` and a residual that shows the
  rest; the residual output is the check, as with the plane. A double exponential is a new method.
- Harder: `amplitude` is referenced to the window's start, not to the physical edge, so for a slow onset
  it is smaller than the step by `exp(−(t_start − t_edge)/τ)`. The attrs carry `t_edge` and `t_start`;
  a caller who wants the step amplitude extrapolates, and the ADR says so rather than the method
  guessing an onset it cannot see.
- Harder: Flight Deck lists every method for every record (`applies_to` is not yet used to filter), so
  the exponential is offered on a map and fails with a 400 that names the shape; and until the
  time-series view exists, its markers and its output curve are stored but not drawn.
- Must now: `applies_to` is read when the time-series view is built (filter the method list by the
  record's shape); the L2-3 bench test, when written, captures the step on the scope through
  `WaveformSense.arm`, builds the record as Probe 03 did, and asserts `tau` against the datasheet.
  There is no waveform-capture activity in `SweepDefinition`, so the server cannot yet produce such a
  record; that is a Step 5 gap recorded in STATUS, not a decision taken here.

## Alternatives considered
- Fitting `t₀` as a free parameter — rejected: degenerate with `amplitude` for a pure exponential;
  identifiable only with a two-regime (baseline then exponential) model, which is a step-response fit
  and does not cover a droop whose pre-edge level is unrelated to its decay.
- A log-linear fit over 10–90 % of the excursion (the probe's estimator) — rejected: it needs the
  asymptote known in advance (from the last samples), gives no standard errors for the asymptote, and
  weights the points unequally in the original units. It is the starting point of the nonlinear fit.
- `t_start` and `t_stop` as absolute times — rejected: `AttrValue` has no None, so "auto" would need
  a sentinel inside the time axis, and a scope's time axis can legitimately contain zero. `skip` and
  `span` are relative to the edge, non-negative, and zero is a natural "none".
- The fitted curve as a `curve` annotation with the value as a pseudo-coordinate — rejected: it would
  break `Dataset.check_annotation` and the rule that overlays live in the record's coordinate system.
  The curve is a Dataset over the same time coordinate (ADR 0031), which the time-series view will draw
  beside the trace.
- Bumping `control`'s schema_version for the new `applies_to` value — rejected: adding a literal value
  invalidates no stored document (`MethodSpec` is never stored) and no old client is broken by a value
  it filters on; ADR 0037 set the precedent for additive changes to a frozen slice.
- Deriving a bandwidth, `1/(2π·tau)`, as an estimate (the probe reported one) — rejected for now:
  a derived quantity with a propagated error is one line for the caller and a second name to keep in
  step; the oracle in BENCH.md is τ.
