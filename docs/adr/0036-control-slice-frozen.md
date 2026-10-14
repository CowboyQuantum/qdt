# 0036 — Control slice frozen at schema_version 1: `Run`, `MethodSpec`, `ParameterSpec`, `EstimateSpec`

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4b (closes it)

## Context
Step 4b's exit criteria are:
- The e2e loop passes in CI and as a scripted demo with only the server running.
- `control.py` is frozen with an ADR.

`control.py` was defined by ADR 0032 and ADR 0034. Over three sessions it has been used by:
- `qdt-server`: the run lifecycle, the method catalogue and the API.
- The Flight Deck panel: its runs list, its method parameter forms and the abort button, all through the
  generated `api.ts`.
- The e2e tests and the API contract tests.

This ADR is the freeze review, field by field, against that use.

- **`Run`.** The server sets every field.
  - The panel reads `run_id`, `definition_name`, `state`, `record_id` and `error`.
  - The lifecycle validator holds for every path the server now takes:
    - queued → running → completed (with a record);
    - running → aborted, with a record of the partial data, since session 3 added
      `POST /runs/{id}/abort`;
    - queued → aborted, with no record;
    - running → failed, with a reason.
  - `attrs` carries the run options (seed, noise, campaign, model overrides), which the API tests read.
- **`MethodSpec`.** Both curated methods have one, pinned to their function signatures by
  `test_catalogue`. The panel builds its forms from the spec alone: defaults, kinds, bounds and units.
  `fit_model` makes the `FitModel` that results carry, which ADR 0033 froze.
- **`ParameterSpec`.** `check` is the server's validation and is mirrored client-side in `methods.ts`.
- **`EstimateSpec`.** The panel lists the promised estimates.

Considered and deliberately left out:
- **A progress field on `Run`.** Progress is visible on the stream: lines arrive, and `Dataset` chunks
  carry their region.
- **An actor or owner on `Run`.** Step 7 brings multi-user; until then it can live in `attrs`.
- **A `trace_1d` value for `applies_to`.** No 1-D method exists yet, even though 1-D sweeps now run.
- **`choices` on a `str` parameter.** The `variable` parameter's choices come from the Dataset, not the
  spec.

Each of these becomes a typed field once a consumer exists, at the normal cost for a frozen object.

`Run` and `MethodSpec` are not persisted: runs live in the server's memory and specs in its catalogue.
They are therefore not in `migrations.PERSISTED` and get no migration fixtures. Three things pin their
wire shape instead:
- v1 examples in `packages/qdt-schemas/tests/test_control.py`, which must validate and dump back
  unchanged;
- the drift-checked OpenAPI export;
- Flight Deck's drift-checked `api.ts`.

## Decision
Freeze `control.py` (`Run`, `MethodSpec`, `ParameterSpec`, `EstimateSpec`) at `schema_version` 1, as of
the commit carrying this ADR. From here a change follows the frozen-object rule. One commit carries:
- the ADR and a version bump;
- the v1 example kept as history next to a new one;
- the regenerated OpenAPI export and `api.ts`;
- every consumer.

Step 4b is DONE:
- **e2e:** `apps/flightdeck/e2e/control.test.ts` passes in CI. It covers the form, an edited pulse
  sequence, the run, the live map, the record, the analysis, the overlays and a 1-D trace.
- **Scripted demo:** `scripts/demo_control_path.py` serves the built UI from `qdt-server` as one
  process.
- **Freeze:** this ADR.

## Consequences
- Easier:
  - Step 5 drivers reach the browser through the same API. A real stand changes the backends behind
    `RunManager`, not the objects the UI renders.
  - Flight Deck can rely on the shape of `api.ts` for these types.
- Harder:
  - Each of the fields left out above now costs a version bump and an ADR.
- Must now:
  - Treat `api.ts` changes to these four types as frozen-object changes in review.
  - When a 1-D method is curated, widen `applies_to` by ADR.

## Alternatives considered
- **Freeze after Step 5, once real runs have exercised `Run`.** Rejected. The step's exit criterion is
  this freeze, and real drivers change the backends, not the lifecycle. ADR 0032 said the API does not
  change for Step 5, so drivers have nothing to add to the shape.
- **Add the left-out fields now, "while it's cheap."** Rejected. None of them has a consumer, and a field
  without a consumer is a guess that the freeze would then make expensive to fix.
- **Put `Run` and `MethodSpec` in `PERSISTED` to reuse the fixture machinery.** Rejected. That would
  claim the registry stores them, which it does not (ADR 0025 defines `PERSISTED` as what is stored).
