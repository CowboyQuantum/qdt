# qdt-analysis — package rules

Pure-functional analysis (rule 5): schema objects and arrays in, `AnalysisResult` out. No I/O, no
registry, no sockets, no files. `scripts/check_imports.py` greps for violations.

## Layout
```
qdt_analysis/
  transitions.py  # charge-transition lines on a 2-D map: detect (ridges → families → runs) / estimate (TLS segments) / charge_transitions (→ AnalysisResult)
  recovery.py     # injection–recovery scoring of a result against a truth mask, in pixels
```

## Rules
- A detector is `f(dataset, arrays, scenario, *, record_id=None, **parameters) -> AnalysisResult`. It
  takes the `ScenarioRef` as an argument (it cannot know what generated the data) and records every
  parameter it used in `FitModel.parameters`, with the defaults in a module-level `DEFAULTS` (ADR 0029).
- Findings are `Annotation`s in the Dataset's own coordinates (`Dataset.check_annotation` must pass), so
  Flight Deck draws them with no analysis-specific code. Per-feature numbers go in `Annotation.attrs`;
  scalar outcomes in `AnalysisResult.summary`. Arrays never go in a result.
- Detection and estimation stay separate stages with their own public functions, so a different
  estimator can reuse the detection and the tests can inspect either.
- Every detector has an injection–recovery test in CI on synthetic data (known injected features) and on
  `SimulatedDevice` data (truth from the model via the scenario ref, e.g. `DoubleDotModel.transition_map`).
  Tests may import `qdt_sim` and `qdt_lab`; the package itself depends on `qdt-schemas`, numpy and scipy only.
- numpy/scipy only; no plotting, no pandas, no QuTiP.
