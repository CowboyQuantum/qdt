# 0045 — The curated plane fit: least squares with standard errors, a minimum explained variance, iso-lines as overlays

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 5

## Context
L2-1 (BENCH.md, ADR 0040) reads a DC level stepped on the outer axis and a pulse amplitude swept on the
inner one, summed through a passive network, at a sink. Its oracle is a plane,
`V = c_DC · V_DC + c_P · V_pulse + offset`, and its pass criterion is the two coefficients against the
network's specification. The step asked for this fit as a curated `qdt-analysis` method with iso-line
overlays (Step 5 deliverables; ADR 0041 said "drivers first, simple; fits later"). The first sweeps on
hardware (session 11, a 16 × 32 map on an OPX loopback) and Probe 03's combiner (DC division 2.525, pulse
side 0.81) now give it real inputs.

The existing methods (ADR 0029, 0030) are edge detectors with a shared detection stage; a plane is a
different kind of method: a global fit with no detection, where the honest output is the coefficients
with their uncertainties and the overlay is derived from the fit, not found in the data. The package rules
still apply: every parameter in the `FitModel`, a `failed` status when there is nothing to report, an
output payload for the arrays, an injection–recovery test.

## Decision
`qdt_analysis.plane.fit_plane` fits `z = slope_row · x + slope_col · y + offset` by ordinary least squares
over the finite points (leading dims averaged first), reports the three coefficients with standard errors
from the residual variance, plus `isoline_slope` (−slope_row/slope_col, with propagated error; absent when
the column slope is zero), `residual_rms` and `r2`; it fails when the plane explains less than `min_r2`
(default 0.5) of the map's variance or the map is constant; it draws `n_isolines` (default 8) `line`
annotations at evenly spaced levels strictly between the plane's extremes over the window, each clipped to
the window and labelled with its level; and its output payload is the fitted plane and the residual over
the input's coordinates. It is in `qdt_server.catalogue` as `qdt_analysis.plane.fit_plane`, version 1.

## Consequences
- Easier: L2-1's pass criterion is a comparison of two estimates and their standard errors against the
  network's specification; the test needs no fitting code of its own. Flight Deck draws the iso-lines
  with no new renderer (they are `line` annotations, like transition segments), and the residual map is
  viewable like any analysis output (ADR 0031), which is where a non-planar network (the combiner's
  low-pass, a loaded sink) will show first.
- Easier: the estimate names are generic (`slope_row`, `slope_col`), so the same method serves any
  two-axis linear response, not only DC + pulse; the caller maps row to DC and column to pulse.
- Harder: ordinary least squares is not robust. A map with transitions or saturation on top of a plane
  fits a biased plane with a small `r2` and large residuals; `min_r2` turns the worst of these into a
  `failed` result, but a map that is half plane, half structure can still pass. The residual map is the
  check; a robust variant would be a new version.
- Harder: `min_r2` is a judgment (0.5), not a statistic. A real L2-1 map scores above 0.99, a noise map
  near 2/N; the threshold sits between to keep a flat loopback (both slopes near zero but a clean plane)
  from passing on noise alone. A caller with a legitimately weak plane lowers it, and the parameter is in
  the `FitModel`, so the result says so.
- Must now: a method that changes any of this (robust weights, a different failure test, iso-line levels
  at round numbers) bumps `VERSION`. The L2-1 bench test, when it is written, calls this method and
  asserts on `slope_row`, `slope_col` and their `stderr` fields.

## Alternatives considered
- A robust fit (Huber or RANSAC) from the start — rejected: the oracle is a clean plane by construction,
  and a robust estimator hides the departures the residual map is meant to show. ADR 0041's order holds:
  simple first.
- Failure by a significance test on the slopes (|slope| / stderr) instead of `r2` — rejected: a flat but
  clean loopback has insignificant slopes and a perfectly good offset, and would fail; and a large map
  makes any slope significant. `r2` says whether the plane describes the map, which is the question.
- Iso-lines at round-number levels (nice ticks) — rejected for now: evenly spaced levels between the
  extremes are predictable (always `n_isolines` of them, always spanning the window) and the label
  carries the exact level. A tick-based variant is a version bump.
- Reporting `isoline_slope` as infinite when the column slope is zero — rejected: an infinite `Estimate`
  does not survive JSON, and a vertical iso-line's slope is not a number to compare against anything.
  The estimate is absent and the spec says so.
- A `polyline` or `curve` overlay per iso-line — rejected: on a plane they are straight; `line` is what
  the recovery scorer and Flight Deck already handle.
