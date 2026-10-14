# 0035 — The Step 4b pulse-sequence editor is a form over `PulseSequence`, not a timeline

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4b — Control path (closes the open decision "where the pulse-sequence editor stops")

## Context
Step 4b's exit asks a user to craft a sweep *with a pulse sequence* from the browser (ADR 0032). Until
session 3 the panel sent a fixed one-step template, `step(inner, v_<inner>) ; measure(sensor)`, so the
sequence could not actually be edited. The step file left open whether the editor is a form over
`PulseSequence` or a graphical timeline.

What constrains the choice:
- `PulseSequence` is frozen (ADR 0022). It is a short list of primitives (`step`, `ramp`, `wait`,
  `drive`, `measure`, plus `call` into named `Segment`s). Any value or duration is a number or a
  `Symbol`, and every symbol has to be bound by the stage (`SymbolBinding`: an axis or a constant).
  There is no control flow.
- Rule: types under `src/schema/` are generated and never hand-coded around (Flight Deck CLAUDE.md). An
  editor whose fields drift from the schema would only fail at the server.
- The step file asks for forms driven by the generated schema, with unit tests from schema to form to a
  valid object.
- The simulator executes `step`, `ramp` (holding the end level), `wait` and `measure`. It lets `drive`
  pass time without any effect. A timeline would draw ramps and drives that the simulated backend does
  not render faithfully.
- 1-D sweeps were also missing from the panel, although the view already draws traces.

## Decision
Make the Step 4b editor a form with one row per primitive in time order and one text cell per field. A
value cell holds a number or a symbol name, and each symbol is bound below the rows to an axis name or a
number. Type-check the columns against the generated `api.ts`. Do not edit `call` and `Segment`s in the
browser. Let either sweep kind drop its outer axis, which makes a 1-D sweep.

## Consequences
- Easier:
  - The whole frozen vocabulary that the simulator runs is reachable from the browser in a small,
    testable module, `src/control/sequence.ts`, which is pure and has no DOM.
  - `OP_FIELDS` is checked against the generated `Step | Ramp | Wait | Drive | Measure` types. A
    compile-time assertion fails `tsc` if a required field has no column, or if a column names a field
    that doesn't exist. A schema change therefore breaks the build, not the run.
  - The editor refuses what the `PulseSequence` and `SequencerStage` validators refuse, naming the op:
    unknown or wrong-quantity channels, non-integer durations, duplicate results, a symbol used in two
    units, unbound symbols. The user sees the errors while typing, before any request is sent.
  - A symbol may take a stepped (outer) axis's value as well as the stage axis's value, because the
    emitter already supported per-run `axis_value` parameters.
  - Bindings that follow the `v_<axis>` convention fill themselves in, so the template still works with
    zero edits.
  - `qdt-server` tests show that what the editor produces compiles and runs on the simulator: a ramp
    with a symbol duration, a wait, a kick on the bias line, two measures, and 1-D stage and DC sweeps.
- Harder:
  - No picture of the shot. A user reads the timing from the rows.
  - A sequence that uses `call`/`Segment`s cannot be authored in the browser.
  - Cell text is parsed loosely: a typo such as `v_P3` becomes a new symbol, not an error. The
    unbound-symbol error then catches it.
- Must now:
  - Treat the editor model as the place to extend. A primitive added to `PulseSequence` by ADR fails
    `tsc` until `OP_FIELDS`, `newRow` and the tests cover it.
  - When a real sequencer arrives (Step 5), restrict the channel choices to that instrument's lines.
    Today new rows only default to the stand's `_pulse` lines.

## Alternatives considered
- **Timeline editor (drag segments on per-channel lanes).** Rejected for 4b. It costs far more for the
  same frozen vocabulary, it is hard to unit-test, and it would show ramps and drives the simulator does
  not render. The form model it would sit on is the one built here, so a timeline can be added later as
  a view over the same rows.
- **A generic JSON-Schema form generator over `PulseSequence`.** Rejected. The `number | Symbol` unions
  and the discriminated op union generate awkward nested forms. Binding symbols is a cross-object rule
  (sequence ↔ stage) that a schema-driven form cannot express. Type-checking a hand-laid form against
  the generated types gives the same guarantee against drift.
- **Editing `Segment`s and `call` in 4b.** Deferred. Segments matter for reuse across experiments, which
  is a library concern and not something a single form needs. A stage may still carry them when built
  elsewhere.
- **Raw JSON text area for the sequence.** Rejected as the main path. It gives no field-level errors and
  no unit hints, and a JSON text area is not the "form" the step asks for.
