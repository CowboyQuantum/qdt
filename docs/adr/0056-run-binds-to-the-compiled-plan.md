# 0056 — One Run, bound to the compiled plan: the Sweep and Pulse widgets, the strip's identity and stale marker

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6b (deliverable 3; extends 0054)

## Context
ADR 0054 put one Run in the strip and said editors never run. The shell (session 1) wired the strip's
Run to the panel's own submit, so two Run controls existed and the strip knew nothing of what would run.
The panel's sweep form and pulse-sequence editor sit over pure, unit-tested models (`control/sweeps.ts`,
`control/sequence.ts`, ADR 0035) and only needed a new presentation. Two questions decide the shape: what
"bound to the compiled plan" means when `POST /runs` takes a definition, not a plan id; and how two widgets
that used to share one form (the pulse template follows the sweep's inner axis and sensor; the stage sweep
takes the sequence) talk when each is a pane the user can open, close or move.

## Decision
- **The Sweep widget holds the plan.** It builds the `SweepDefinition` (stage, DC or capture, with the
  operating-point levels of ADR 0038) and compiles it on the server (`POST /sweeps/compile`). The compile
  response's `plan_id` and a one-line summary (axes, points, channels, a stage program) go to the strip
  (`plan:compiled`) and into the widget. Any later edit, in the Sweep or the Pulse widget, marks the plan
  **stale** (`plan:changed`): the strip shows "plan 1234abcd · stale".
- **Run runs what the editors hold.** The strip's Run (`run:request`) is answered by the Sweep widget: if
  the last compile is current it starts that definition; if it is stale or absent it compiles first, then
  runs. The identity in the strip is therefore always of a plan that was compiled from the editors' state,
  and never of a plan the editors have moved past. Requiring a manual recompile before every run was
  rejected as friction at a bench; the stale marker tells the user the shown identity is old, Run never
  runs it. The server compiles again on `POST /runs`; the run's own plan id is its record's.
- **One run at a time from the UI.** The Sweep widget follows the run it started (`run:state`); the strip
  shows "run 1234abcd name · state → record" and an abort button; Run is disabled while a run is live. The
  panel's Runs list is gone; completed runs are records in History.
- **Sweep and Pulse talk over the bus.** The Sweep widget publishes its axes, inner channel and sensor
  (`sweep:axes`); the Pulse widget follows the one-step template for them until edited and publishes its
  rows, bindings and errors (`pulse:sequence`); the Sweep widget keeps the latest and refuses a stage sweep
  while the sequence has errors or no Pulse widget is open. Both re-publish on `layout:changed`, so a pane
  opened later catches up. The pure models are unchanged.
- **The panel shrinks** to the held operating point (click-to-set), records, analysis and the tune-up
  runner, which gets its own options field (it used to read the sweep form's). Deliverables 4–5 take the
  rest and delete it.
- **The default layout** is sweep + control | plot | pulse + history, under a versioned storage key
  (`flightdeck.layout.v2`): a stored v1 layout would hide the new widgets, so it is retired rather than
  migrated.

## Consequences
- Easier: exactly one Run control with a visible identity and a stale marker (the step's exit criterion);
  the sweep and pulse editors are panes like any other; e2e tests drive the strip.
- Harder: a stage sweep needs the Pulse widget mounted (its sequence lives there); closing it makes the
  next stage Run fail with a clear message. The strip follows one run; a second Run while one is live is
  refused (the server could queue it; the UI does not yet).
- The compile response is fetched for the identity only; nothing else reads the `ExecutionPlan` yet
  (a plan viewer is a later widget).

## Alternatives considered
- Run disabled while stale, compile mandatory — rejected: two clicks per run at a bench, for an identity
  the user rarely reads.
- `POST /runs` by plan id (server-side plan cache) — rejected for now: an API change for a UI nicety;
  the definition is the contract (ADR 0032, 0036). Revisit if plans grow expensive to compile.
- One widget for sweep and pulse — rejected: the prototype and ADR 0054 keep them separate panes; the bus
  pair (`sweep:axes`, `pulse:sequence`) is the whole coupling.
