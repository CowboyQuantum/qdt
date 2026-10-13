# 0031 — Analysis outputs are Datasets in payloads; methods are curated; one record per result for now

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4

## Context
After seeing the Step 4 overlays in Flight Deck, the human reviewed the shape of the analysis objects
(ADR 0029: `FitModel`, `Estimate`, `AnalysisResult`) against the end state: analyses run from a web
app, not from a terminal. Three things were decided on 2026-10-13:

1. The web app runs **curated** analyses. Users do not author methods in the browser. A method is code
   in this repo or the internal extension, declared with a name, a version and its parameters.
2. **Multi-record analyses are deferred.** Longitudinal studies across records may well live in a
   consumer's own environment; a result keeps one `record_id`.
3. A result must be able to carry **arrays, and several of them**, so an analysis can produce a graph of
   its own: a fitted map, a residual, the image it detected on, a derived curve. The objects had only
   scalars (`Estimate`) and overlays (`Annotation`), and records never embed arrays (ADR 0001).

The repository already has one shape for named arrays with coordinates and units, in two forms: the
`Dataset` stream contract (Flight Deck draws it) and the `qdt-hdf5-v1` payload (the registry stores it).

## Decision
An analysis output is a `Dataset` of its own, with `source.kind = "analysis"`, written as a
`qdt-hdf5-v1` payload and referenced from the result by `AnalysisResult.output: PayloadRef | None`. A
method returns `Analysis(result, output)`: the `AnalysisResult` and the output as an in-memory `Payload`
(dataset, arrays, annotations), or None. The method stays pure; `Registry.add_result(result, output)`
writes the payload once to the store at `analysis/<YYYY>/<MM>/<result_id>.h5`, fills `result.output`
with its reference and returns the stored result. `Registry.output(result_id)` reads it back; `sync`
uploads it before the result row, as a record's payload goes before the record; `python -m qdt_registry
serve --output <result_id>` streams it to Flight Deck, where it renders like any measurement.

The first outputs are the detection maps of both Step 4 methods (gradient magnitude and edge mask over
the input's coordinates, with the segments drawn on them): what the detector saw, kept even when the
method failed.

`"analysis"` is a new member of the frozen `SourceDescriptor.kind`. By the frozen-object rule
(ADR 0015, `packages/qdt-schemas/CLAUDE.md`) that is `Dataset` v2 with an identity migration, and, by the
nested-version rule of `migrations.py`, `ExecutionPlan` v2 whose migration upgrades its nested Dataset.
Both keep their v1 fixtures; `data.schema.json`, `records.schema.json` and Flight Deck's generated types
are regenerated. The wire decoder reads Datasets through `migrations.load`, so a v1 recording replays
as v2. No table changed (`DDL_VERSION` stays 2): the output reference lives in the result body, as the
payload reference lives in a record body.

The curated-methods decision means the method catalogue the web app needs (name, version, parameter
schema for its form, applicable dataset shapes, promised estimates) is a declared object over existing
code, not a user-authoring surface. It enters with the server that runs methods from the UI, which the
roadmap does not yet have a step for; `FitModel` as it stands is what that catalogue entry will embed.

## Consequences
- Easier: one array contract. An output is viewable, storable, syncable and replayable with code that
  already exists; the modeling slice did not grow an array type. Several arrays are several variables of
  one Dataset, on shared coordinates, which is what a graph needs.
- Easier: results and outputs separate cleanly. A result without arrays costs one row; a result with
  arrays costs one file, immutable and content-addressed like a measurement payload.
- Harder: an output's Dataset id is `<result_id>-detection`-style and is not a plan id, so `records`
  cannot index it; "which outputs decorate dataset X" is a scan of result bodies until a link table is
  justified.
- Harder: the two frozen-contract bumps are the first in the repo. They are formalities for readers (the
  migrations are identity apart from the nested upgrade), but any client pinned to v1 must upgrade to read
  new datasets.
- Must now: a method that produces arrays returns them as a `Payload` whose Dataset says
  `source.kind="analysis"`; the registry refuses any other kind. Tests read fixtures through
  `migrations.load`, never `model_validate` of a fixture file.

## Alternatives considered
- Arrays inline in `AnalysisResult` (base64 or lists) — rejected: records never carry arrays (ADR 0001,
  0025); results sync as rows and would bloat.
- A dedicated `AnalysisOutput` array type — rejected: it would duplicate `Dataset` (names, dims,
  coordinates, units, dtypes) and need its own renderer and storage.
- Reuse `source.kind = "registry"` or `"synthetic"` for outputs to avoid touching the frozen contract —
  rejected: both lie about the producer; the bump is cheap and the kind is useful to consumers.
- A user-authoring surface for methods — rejected by the human for the web app; code stays curated.
- Multi-record inputs now — deferred by the human; `record_id` stays singular and a link table can be
  added without changing the result's meaning.
