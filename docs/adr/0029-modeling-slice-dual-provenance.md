# 0029 — `modeling.py`: `AnalysisResult` with dual provenance; a scenario ref is a generator name plus seed

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4

## Context
Step 4 makes analysis a consumer of the registry: a fit or detection runs on a recorded measurement,
emits an `AnalysisResult` "with dual provenance", and renders as `Annotation` overlays in Flight Deck.
Plan §4.1 names the Step 4 objects (`FitModel`, `AnalysisResult`) and the L0 test "`AnalysisResult`
carries measurement ref + scenario ref; missing either fails validation", but nothing in the repo said
what a *scenario ref* identifies. Asked on 2026-10-13, the human chose: a `qdt_sim` scenario name plus
the seed, over reusing the stand/activity identity or the registry record id.

What the consumer needs, from the first detector (charge-transition lines on a stability diagram):
a way to say which Dataset and variable it ran on and which record holds it; a way to regenerate the
data's truth so CI can score the detector (injection–recovery); the detector's name and parameters, so
a result can be repeated; findings in the Dataset's coordinates, so Flight Deck draws them with the
annotation overlay it has had since Step 1; and scalar summaries. Arrays are not needed.

## Decision
`modeling.py` holds four objects, all at `schema_version` 1:

- `FitModel`: `name`, `version`, scalar `parameters`. What ran, and how.
- `MeasurementRef`: `dataset_id`, `variable`, optional `record_id`. What it ran on. The record is
  optional in the schema, because a result on unrecorded data (a synthetic map in a test) is still a
  valid result; the registry refuses to store a result without it.
- `ScenarioRef`: `kind` (`simulation` | `synthetic`), `name`, `seed`, scalar `parameters`. What
  generated the data. For `simulation`, `name` is a key of `qdt_sim.scenarios.SCENARIOS` and
  `qdt_sim.scenarios.resolve` rebuilds the sweep, the stand and the seeded device; tuple arguments
  travel as `<axis>_start` / `<axis>_stop`, and `noise` / `sample_charge` configure the device. For
  `synthetic`, the generator is a test's; `name` + `seed` identify it.
- `AnalysisResult`: `analysis_id` (client-minted UUID4 hex, ADR 0024), `model`, `measurement`,
  `scenario`, `annotations`, `summary`, `created_at`, `attrs`. Both provenance legs are required fields.
  Every annotation must carry `measurement.dataset_id`, and ids are unique within a result.

`AnalysisResult` joins `migrations.PERSISTED` with a fixture, and `records.schema.json` exports it. The
slice is **not yet frozen**: the step file freezes it at exit, after the Flight Deck demo, with its own
ADR.

## Consequences
- Easier: injection–recovery is a CI test with no fixtures of "expected lines": the scenario ref on the
  result regenerates the model, and `DoubleDotModel.transition_map` is the truth. Repeating an analysis
  is `charge_transitions(**result.model.parameters)` on the same record. Flight Deck needs no change to
  show results: they are annotations on the originating Dataset.
- Harder: live data (Step 5) has no generator. `ScenarioRef.kind` has no `live` member on purpose; the
  Step 5 ADR decides whether a live measurement's second leg is a `none` kind, a stand/activity ref, or
  something else, and whether `scenario` becomes optional for it. Until then every result is on
  simulated or synthetic data, which is all Steps 1–4 produce (ADR 0007).
- Harder: `parameters` on both refs are flat scalars (`AttrValue`), so a scenario with structured
  arguments has to flatten them (as the ranges do). Step 6's `SimScenario` is the place for structure.
- Must now: a `ScenarioRef` names a scenario in `SCENARIOS`; adding a scenario adds a key there. A
  detector in `qdt-analysis` returns an `AnalysisResult` and nothing else, takes the scenario as an
  argument (it cannot know it), and records every parameter it used in `FitModel.parameters`.

## Alternatives considered
- Scenario ref = the Step 2 stand/activity identity (`stand_id` + definition hash) — rejected: it says
  what was swept, not what the data *is*; the truth of a simulated run is in the model and the seed.
- Scenario ref = the registry record id — rejected: it duplicates the measurement leg and says nothing
  about the physics; injection–recovery would need a side channel to find the model.
- Put the detector's parameters on the result's `attrs` — rejected: `FitModel` makes "what ran" a typed,
  queryable object; `attrs` stays free-form.
- Carry a `truth` array or expected lines on the result — rejected: results never carry arrays
  (ADR 0001), and the truth belongs to the scenario, not to the analysis.
