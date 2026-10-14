# 0038 — A sweep carries its operating point: fixed DC levels held for the whole scan

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 4b follow-up, before Step 5 (the human's choice, 2026-10-14)

## Context
A `SweepDefinition` said what to step, what to sense and what the sequencer runs, but not where the
other gates sit.

In a stage sweep the inner gate is pulsed on its `_pulse` line, and a pulse **adds to that gate's DC
level**. That level was whatever the instrument last had:
- in the simulator it is 0, so pulse levels only *looked* absolute;
- on hardware it is whatever the previous experiment left.

The plunger not being swept, the sensor gate and the bias were all unspecified the same way. The record
did not say where they were either, so a measurement could not be reproduced from its definition.

The human hit this while assigning levels in the Step 4b demo, and chose to fix it before Step 5's real
instruments.

The same versioning constraint as ADR 0037 applies: the registry recomputes `SweepDefinition`'s content
hash from stored payloads. So the addition must leave definitions without an operating point serialized
exactly as before.

## Decision
Add `SweepDefinition.levels: tuple[FixedLevel(channel, value), ...]`.
- Each level is set once before the scan, settled once (the longest `settle_s`), and held throughout.
- A level holds a `LevelSource` channel that the sweep neither steps nor senses, one level per channel.
  Compile resolves each one as `level_source`, so it shows up in the plan's channels.
- The field is excluded from serialization when empty (pydantic `exclude_if`), so every existing
  definition keeps its hash. No version bump, no migration.

## Consequences
- Easier:
  - A definition fully states the gate voltages it ran at. A recorded payload carries the definition,
    so the record now holds the operating point.
  - A stage sweep can sweep the inner gate's pulse around a chosen DC point. The simulator test pins
    the arithmetic: DC 50 mV with pulse −20…120 mV gives the same map as DC 0 with pulse 30…170 mV.
  - The panel has an "operating point" section, checked live against the swept channels.
- Harder:
  - Levels are held but not restored after the run. On hardware the gates stay where the sweep left
    them, which is the usual lab behaviour. A "return to" field would be a later addition.
- Must now:
  - Step 5 drivers apply levels through `LevelSource.set` like any stepped axis. Ramp-rate limits for
    large DC jumps are a driver concern, set by the protocols in ADR 0021.
  - A default operating point per device (for example, stored on the `DeviceRecord`) is not part of
    this decision. If it is wanted, it gets its own ADR.

## Alternatives considered
- **Axes with `num = 1` as fixed levels.** Rejected. Each would add a length-1 dimension to the
  Dataset, which is semantically wrong and clutters every view and analysis.
- **Operating point in `attrs`.** Rejected. Nothing would apply it, and compile would not check it.
- **Per-run options on `POST /runs`.** Rejected. The operating point is part of the experiment and must
  be in the definition, so that it is recorded and hashed.
- **A defaulted, always-serialized field with a `SweepDefinition` v2 bump.** Rejected for the re-ingest
  hash failure (ADR 0037).
