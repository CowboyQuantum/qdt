# 0027 — Flight Deck may read `source.registry_ref`, for display only

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 3

## Context
Rule 8 says Flight Deck never knows which instrument produced a `Dataset`. A test in
`apps/flightdeck/test/render.test.ts` enforces it bluntly: no file under `src/` may mention `dataset.source`
at all. Step 3's deliverable "datasets addressable by record ref" put the record id of a registry replay into
`SourceDescriptor.registry_ref`, a field the frozen contract has carried since ADR 0015. Under the blunt test,
Flight Deck could not show which record it was displaying. The human asked on 2026-10-13 to allow it, after
being told the downside.

The downside is erosion. Once `.source` is readable, branching on `source.kind` ("simulation renders
differently") is one line away, and source equivalence (the same `Dataset` renders identically from any
source) would quietly stop holding. `registry_ref` itself carries no producer information. It is a registry
record id, assigned after the fact, and it says nothing about the instrument.

## Decision
Allow exactly one read, `dataset.source.registry_ref`, used only to label the view (the title shows
`· record <id>`). The rule-8 test keeps forbidding every other access to `.source`, including `kind`, `label`
and the object itself, and gains a self-test proving the pattern still catches those.

## Consequences
- Easier: a replayed record is identifiable on screen, which is what "addressable by record ref" needed.
- Harder: the guard is now a regex with an exception rather than a total ban, so it is slightly easier to
  misread. The self-test pins its behaviour.
- Must now: `registry_ref` never changes what is drawn, only the title. Any further read of `.source`
  (showing `kind`, for example) needs its own ADR. Rendering stays a function of the `Dataset`'s shape and
  data only.

## Alternatives considered
- Keep the total ban and print the record id only on the server side (`python -m qdt_registry serve`) —
  rejected by the human: whoever looks at the screen should see which record it is.
- Allow all of `.source` for display (kind, label, ref) — rejected: `kind` is the field whose use
  invites branching on the producer, and nothing on screen needs it yet.
- Put the record id into `Dataset.name` or `attrs` on replay — rejected: it duplicates a field the contract
  already has for this purpose, and changes the Dataset between live and replayed views.
