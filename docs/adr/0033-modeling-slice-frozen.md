# 0033 — Modeling slice frozen at schema_version 1: `FitModel`, `Estimate`, `AnalysisResult`

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4

## Context
Step 4's exit criteria are a fit that runs from a query, writes an `AnalysisResult`, and renders as an
overlay on the originating dataset (seen by the human in Flight Deck on 2026-10-13), injection–recovery
in CI, and the `modeling.py` slice frozen with an ADR. The slice was defined by ADR 0029, exercised by
ADR 0030's second method, and amended by ADR 0031 after the human's review of its shape against the end
state (curated methods, single record, array outputs). This ADR is the freeze review, field by field
against what the two methods, the registry, Tutorial 03 and the demo actually use.

- `FitModel` (`name`, `version`, `parameters`): both methods fill every parameter including defaults;
  the registry indexes `method_sha256`; results are comparable by it. Step 4b's `MethodSpec` will embed
  it, which is why `parameters` stays a flat scalar dict rather than a nested schema.
- `Estimate` (`name`, `value`, `stderr`, `unit`): eleven estimates across the two methods, all with units.
  No method sets `stderr` yet; it stays optional so a fitting method can.
- `AnalysisResult`: `result_id` and `record_id` (client-minted, the registry's keys), `dataset_id` (the
  overlays' target; checked by the validator), `method` + `method_sha256` (checked), `status` and
  `message` (both methods return `failed` on noise or an incomplete diamond; `serve` filters on `ok`),
  `estimates` (unique names), `annotations` (unique ids, all on `dataset_id`), `output` (ADR 0031;
  filled by the registry), `created_at`, `attrs` (the analysed variable, thresholds, counts).

Considered and deliberately left in `attrs` for now: an actor or trigger of the analysis, a quality
figure, a review or supersession link, a richer status. Each would be a typed field once a consumer
exists (the web app of Step 4b for actor and quality; Step 6 for supersession). Adding them later is a
`schema_version` bump with a migration, which is the normal cost of a frozen object.

## Decision
Freeze `modeling.py` (`FitModel`, `Estimate`, `AnalysisResult`) at `schema_version` 1 as of the commit
carrying this ADR. From here a change follows the frozen-object rule: ADR, version bump, migration,
old-version fixture, every consumer in the same commit. Step 6's `SimScenario`, `SimResult` and
`CalibrationNode` are additions to the module, not edits of these three.

Step 4 is DONE: all exit criteria met, the L0 ladder green in CI, the scripted demo
(`scripts/demo_analysis.py`, with and without `--diamonds`) seen by the human.

## Consequences
- Easier: Step 4b can build `MethodSpec` and the results UI on a fixed result shape; `records.schema.json`
  and the `analysis_results` DDL are stable references.
- Harder: the first typed actor, quality or supersession field is a v2 with a migration.
- Must now: a new method returns an `AnalysisResult` exactly as frozen; what it needs beyond that goes
  in `attrs` until an ADR adds it.

## Alternatives considered
- Add actor, quality and supersession before freezing — rejected: no consumer exists yet, and ADR 0025's
  rule is to add what a step consumes, not what a later one might.
- Freeze only `AnalysisResult` and leave `FitModel` open for `MethodSpec` — rejected: `MethodSpec` embeds
  `FitModel` as is; keeping it open would make results' method hashes unstable.
