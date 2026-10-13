# 0029 — `AnalysisResult` provenance is record + method; transitions are detected locally and estimated as a lattice

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4

## Context
Step 4 asks that fits and detections emit an `AnalysisResult` with "dual provenance: measurement ref +
scenario ref", that a missing ref fails validation, and that injection–recovery runs in CI. Nothing defined
"scenario ref", and `SimScenario` is a Step 6 family. On 2026-10-13 the human chose the reading that applies
to real and simulated data alike: the second ref identifies the analysis *method*.

The first consumer is charge-transition detection on `SimulatedDevice` stability diagrams. Prototyping
showed three things that shaped the estimator:

- A median-plus-MAD threshold finds nothing on a dense honeycomb. Transitions cover too much of the map
  for the median to be "background".
- Gradient directions of a pixelated step are biased toward the diagonal by about 3–4°, even on exact
  occupation maps. Per-segment line fits are worse on `SimulatedDevice` data, because thermal charge
  sampling makes boundary pixels jagged and breaks lines into 10–17 px pieces (10–14° fitted vs 22°
  true).
- The honeycomb's strongest structure is its *lattice*. In the constant-interaction model the pattern
  repeats whenever the gate-induced charge on a dot changes by one electron, so its reciprocal lattice
  vectors are exactly the rows of `C_gate / e`: electrons per volt on each dot from each gate. These are
  the numbers a virtual-gate matrix is built from. The Fourier transform of the gradient-magnitude map
  recovers them with no pixel-grid bias. In a window where both dots are occupied: diagonal within 1%,
  cross terms within about 0.1 aF-equivalent, across noise, seeds and 64–128 px.

## Decision
`modeling.py` adds `FitModel` (method name, version, every parameter), `Estimate` and `AnalysisResult`.
`AnalysisResult` requires `record_id` and `method`, plus `method_sha256`, which must equal the method's
content hash. Its overlays are ordinary `Annotation`s on the record's Dataset. `SimScenario` stays in
Step 6, and injection truth lives in tests (`DoubleDotModel.charge_lattice`).

`qdt_analysis.transitions.detect_transitions` separates its stages:
- **Detection:** a relative and noise-floor threshold, non-maximum suppression, two gradient-direction
  families, and connected segments. Each segment becomes a line overlay.
- **Estimation:** the charge lattice, from the two shortest non-collinear peaks of the zero-padded power
  spectrum of the gradient magnitude, reported as `a_*`/`b_*` electrons per volt and `cross_ratio_a`/`b`.

The registry stores results in a new `analysis_results` table (`DDL_VERSION` 2). The upgrade from
version 1 only adds that table. `serve` publishes a record's stored overlays.

## Consequences
- Easier: every result answers "which data, which method, which parameters" without a second lookup, and
  two results are comparable by `method_sha256`. Flight Deck draws overlays with no analysis-specific code
  (rule 8 untouched). The lattice estimate is the quantity tuning needs next (virtual gates, Step 6).
- Harder: the lattice estimate assumes a periodic region. The empty-dot corner biases cross terms by about
  6% at the default window, which is why tests and the tutorial use an occupied window. Real devices with
  strong tunnel coupling or nonlinear lever arms will need a local estimator or a windowed spectrum. That
  is a new method version, not a schema change.
- Harder: the segments are a display product. Their per-segment slopes are not reported, because they
  are biased (see Context).
- Must now: an analysis method bumps `VERSION` when the same inputs could give a different result. A
  registry upgrade is automatic only across `ADDITIVE_UPGRADES` (new tables); anything else needs the
  migration tooling ADR 0026 deferred.

## Alternatives considered
- "Scenario ref" as the simulation scenario (name + seed) — rejected by the human: it would make real
  measurements unanalysable until Step 6.
- Report transition-line slopes from segment fits or from a Hough or projection-sharpness search —
  rejected after prototyping: biased by pixel quantisation and by sampled-charge jaggedness. Projection
  sharpness locks onto the lattice directions instead, which is what led to the lattice estimator.
- Store results inside the payload file — rejected: payloads are immutable (ADR 0028), and a record may
  be analysed many times by many methods.
