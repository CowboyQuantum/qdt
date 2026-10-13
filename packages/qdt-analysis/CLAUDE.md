# qdt-analysis — package rules

Pure functions: schema objects (and the arrays a `Payload` carries) in, `AnalysisResult` out (rule 5).
No file, network or database access, and no `qdt_registry` import. The caller queries the registry and
stores the result.

## Layout
```
qdt_analysis/
  transitions.py  # detect_segments (shared detection stage: threshold + NMS + direction families + runs); detect_transitions (+ lattice estimate), ADR 0029
  diamonds.py     # detect_diamonds: edges via detect_segments; estimate_diamonds (degeneracy points, period, apex → E_c, lever arm), ADR 0030
  recovery.py     # injection–recovery scoring of line overlays against a truth mask, in pixels
```

## Rules
- Every method has a dotted `NAME` and a `VERSION`, and puts *every* parameter (defaults included) into
  its `FitModel`. Bump `VERSION` whenever the same inputs could give a different result.
- Separate detection (what to draw: `Annotation`s on the record's Dataset) from estimation (what to
  report: `Estimate`s). Report only estimates whose bias is understood (ADR 0029).
- A method that finds nothing returns `status="failed"` with a message. It never invents overlays or
  estimates, and a pure-noise test pins this.
- Injection–recovery is the test: inject truth (a synthetic lattice or diamond train, or `qdt_sim` model
  parameters through the real sweep path), recover it within stated tolerances; `recovery.score` checks
  overlays against the model's lines. Tests may import `qdt_lab` and `qdt_sim`; `src/` may not.
- Edge-based methods share `detect_segments`. A change to it changes every method's output: bump each
  `VERSION`.
