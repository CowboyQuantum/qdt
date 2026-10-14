# 0037 — Chopped readout: `Affine` values and a `difference` primitive, added without a version bump

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 4b (follow-up from the human's demo); amends the pulse slice frozen by ADR 0022

## Context
After using the Step 4b demo, the human asked for a **chopped readout**: two measure points in one shot,
subtracted from each other. The reference point sits a fixed distance from the swept level, and the
difference should be recorded so that views and analyses can use it.

The frozen `PulseSequence` (ADR 0018, 0022) cannot express this:
- **The reference level cannot follow the sweep.** A value is a number or a bare `Symbol`, so
  `v_P2 + 2 mV` cannot be written. Chopping on the other plunger's pulse line moves a different gate,
  which is a different measurement.
- **The difference is not a result.** Two `measure`s record two variables, and nothing records `a − b`.
  With shots averaged the two orders agree (mean(a) − mean(b) = mean(a − b)), but a recorded
  difference is what the user looks at and analyses. On hardware (Step 5) it is also what the sequencer
  should compute, so that it can be averaged or kept per shot without doubling the data.

The two changes also differ in where their natural home is:
- A level "swept value + offset" is a property of the value, so it belongs where values live.
- `a − b` is computed per shot, after both measures and before any reduction. A real sequencer computes
  it inline in the program (QUA assigns and saves a variable), in time order after the second measure.
  It is not a property of the stage's loops.

**Versioning constraint.** Any edit to these nested types changes how definitions and plans are
versioned and hashed:
- `PulseSequence` and `SequencerStage` are not persisted on their own. They live inside
  `SweepDefinition` and `ExecutionPlan`, whose top-level `schema_version` is the only one read.
- Bumping `SweepDefinition` to v2 would change the content hash of every migrated definition, because
  `schema_version` is part of the dump.
- The registry recomputes `definition.content_sha256()` from a stored payload when it ingests, and
  compares it with the record's `definition_sha256` (ADR 0025, 0028). It also keys object rows by plan
  and stand hashes.
- So a bump, or any new defaulted field that gets serialized, would make payloads recorded before the
  change un-ingestable.
- ADR 0031 bumped `Dataset` and `ExecutionPlan` without this problem only because nothing compares
  their hashes. ADR 0031 also added `AnalysisResult.output` at v1 without a bump, which is a precedent
  for additive changes that leave old data valid.

## Decision
Add two **union members**, with no new defaulted field on any existing type and no version bump:
- **`Affine`** (`symbol`, `scale` = 1, `offset` = 0) as a third form of `Value`, beside numbers and
  `Symbol`. It applies to levels, ramp ends, frequency, phase and amplitude, but not to durations. It
  counts as a use of its symbol for units and bindings, so a chop needs no extra binding. The device
  applies `scale·v + offset`.
- **`Difference`** (`op = "difference"`, `result`, `a`, `b`) as a `PulseSequence` primitive:
  `result = a − b` per shot.
  - `a` and `b` must be distinct measures earlier in the expanded shot, in the same quantity (checked by
    the emitter).
  - It takes no time.
  - It is a result like a measure: unique name, reducible, and a data variable in the sensor's unit,
    recorded beside `a` and `b`.

Existing objects serialize byte-for-byte as before. A test now pins this: the current fixtures of the
three hashed types (`ExecutionPlan`, `StandConfig`, `SweepDefinition`) must re-serialize unchanged.

## Consequences
- Easier:
  - A chopped readout is five rows in the editor: step `v_P2`, measure, step `v_P2 + 0.002`, measure,
    difference.
  - The difference is a recorded data variable, so views, `serve` and curated methods (via their
    `variable` parameter) can use it.
  - Every stored payload, record hash and fixture stays valid, and no migration is needed.
  - Flight Deck's coverage check now derives the primitives from the generated union. It failed `tsc` on
    `difference` until the form supported it, which is the guarantee ADR 0035 promised.
- Harder:
  - An object labelled `schema_version` 1 may now contain constructs that an older reader rejects. Such
    a reader fails with a validation error instead of "newer version than this package". The workspace
    versions all packages in lockstep, so no older reader exists in practice.
  - The pulse vocabulary has one non-channel primitive. Emitters must treat it as computation, not
    timing.
- Must now:
  - The Step 5 QUA emitter implements `Affine` (real-time arithmetic) and `difference` (an assigned
    variable, saved to its own stream).
  - A future change to these slices that is not additive takes the version bump and must also solve the
    re-ingest hash problem, for example by having the registry hash the definition as stored, not as
    upgraded. That is ADR-level.

## Alternatives considered
- **`scale`/`offset` fields on `Symbol`.** Rejected. As defaulted fields they would serialize into every
  existing definition and change its hash. A bare symbol would also stop being the simple thing it is.
- **Derived results on `SequencerStage` (a `derived` field).** Rejected. A defaulted field there
  changes every existing stage's hash unless it is hidden from the dump, and a custom serializer would
  make the generated JSON Schema and TS types unreliable. The computation also belongs in the shot's
  time order, not beside the loops.
- **Only a client-side A − B view.** Rejected by the human: the difference has to be recorded and
  usable by analyses. A client-side difference view is still useful for exploring any two variables,
  and is added separately.
- **Bump `SweepDefinition`/`ExecutionPlan` with identity migrations, following the Dataset v2
  precedent.** Rejected for the re-ingest hash failure described in Context.
- **A second pulse line on the same gate for the chop.** Rejected. It is not a stand most labs have,
  and the offset belongs in the value, not the wiring.
