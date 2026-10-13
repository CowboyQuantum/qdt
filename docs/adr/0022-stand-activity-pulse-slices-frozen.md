# 0022 — Stand, activity and pulse schema slices frozen at schema_version 1

**Status:** Accepted
**Date:** 2026-10-12
**Step:** 2

## Context
Step 2's schema slice is `stand.py` (`InstrumentConfig`, `ChannelMap`, `StandConfig`), `activity.py`
(`SequencerParameter`, `SequencerResult`, `SequencerProgram`, `SweepAxis`, `SensedLevel`, `SymbolBinding`,
`ParameterBinding`, `SequencerStage`, `SweepDefinition`, `ResolvedChannel`, `ExecutionPlan`) and `pulse.py`
(`Symbol`, `Step`, `Ramp`, `Wait`, `Drive`, `Measure`, `Call`, `Segment`, `PulseSequence`). The step file's
exit criterion requires them frozen with an ADR. ADRs 0017, 0018 and 0019 designed them.

Before freezing, a review checked each object against its consumers: `compile_sweep`, `Executor`,
`SimulatedEmitter`, `SimulatedDevice`, the `qdt_sim` scenarios and tutorials 00–01. A `SweepDefinition`
round-trips through JSON, compiles, runs on `SimulatedDevice` and streams live to Flight Deck, and the human
confirmed the rendered map on 2026-10-12. The review found:

- **No object needed a structural change.** Every field is read by at least one consumer, apart from the
  free-form `attrs` and `InstrumentConfig.settings`, which is reserved for Step 5 driver settings.
- **`ResolvedChannel` and `ExecutionPlan.stand_id` lacked constraints** that their sources (`ChannelMap`,
  `StandConfig`) already enforce: non-empty ids, `settle_s ≥ 0`, `integration_s > 0`. The constraints were
  added in commit 60ae1c7. Every plan `compile_sweep` can produce already satisfied them, so this is not a
  breaking change and no version bump or migration was needed.
- **`pulse.py` named its type alias `Quantity`**, the same name as `stand.Quantity` (the physical-quantity
  literal). It was renamed `Value`. A type alias does not appear on the wire or in the JSON Schema.
- `StandConfig.instrument_channels` was added, as a method rather than a field, for the construction
  convention of ADR 0021.

What `SimulatedDevice` does not yet model does not change the schema. `Drive` only advances the clock,
`Ramp` is read at its end value, and there is no tunnel coupling, spin or Pauli blockade (ADR 0020). Each
is a physics addition behind the same vocabulary.

## Decision
Freeze the stand, activity and pulse slices at `schema_version` 1, as they stand at commit 60ae1c7. From
here they change only as `packages/qdt-schemas/CLAUDE.md` prescribes for frozen objects: an ADR, a
`schema_version` bump on the changed object, a pure-dict migration, a fixture at the old version, and every
consumer updated in the same commit.

## Consequences
- Easier: Step 3's registry can persist `StandConfig`, `SweepDefinition` and `ExecutionPlan` as stored
  objects, with the plan as the record of what ran, knowing their shape is fixed. Step 5's QUA emitter
  targets a fixed `PulseSequence` vocabulary and a fixed `SequencerProgram` envelope.
- Harder: the pulse vocabulary is closed at six primitives with no control flow (ADR 0018). Conditional
  operations, feedback or new primitives need an ADR, a version bump and an emitter change on every
  backend. Pre-freeze, this was a one-line edit.
- Harder: `SimulatedEmitter`'s parameter naming scheme (`n_<axis>`, `<sym>_start`, `<sym>_step`, `shots`)
  is not schema, but it lives inside frozen `SequencerProgram` bodies recorded in plans. Changing it means
  old plans no longer re-run on a newer `SimulatedDevice`, so treat it as versioned through
  `SequencerProgram.attrs["emitter"]`.
- Must now: the JSON Schema and DDL exports of these objects are generated from Step 4 onward (package
  rule 6). Until then the field descriptions are the documentation. A new family (for example, calibration
  or tuning objects) enters in the step that first consumes it and is frozen at that step's exit, as this
  slice was.

## Alternatives considered
- Freeze `stand.py` and `pulse.py` but keep `activity.py` open until the registry (Step 3) has stored
  plans. Rejected: the registry stores what Step 2 produces, and a moving `ExecutionPlan` would make the
  first stored records the first migration fixtures. Freezing now lets Step 3 test against a fixed shape.
- Bump `schema_version` to 2 for the tightened `ResolvedChannel` and `ExecutionPlan` constraints. Rejected:
  every value the compiler could ever emit already met them, so no reader-visible data changes and a
  migration would be the identity.
- Close the pulse vocabulary later, after the QUA emitter (Step 5). Rejected: ADR 0018 deliberately kept it
  minimal and grows it only by ADR. Freezing it changes only the cost of growth, not whether growth is
  allowed.
