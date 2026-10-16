# 0058 — The panel is gone: Analysis and Tune-up as widgets; a record is chosen by id, from History or a picker

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6b (deliverable 5; extends 0054)

## Context
`control/panel.ts` was Step 4b's one control surface; ADR 0054 decided to decompose it one widget per
session and delete it when the last widget landed. After ADR 0055–0057 it held the records list, the
analysis form and the tune-up runner. Two of those are widgets in their own right; the records list is
History already. What remained to decide was how an analysis names its record once the list that offered
"analyse" lives in another pane, and how the e2e tests drive the widgets.

## Decision
- **Analysis widget** (`widgets/analysis.ts`): a record picker over `GET /records` (newest first) and a
  method picker over `GET /methods`, the parameters as a form over the pure `control/methods.ts`, run,
  estimates, "show overlays" and "show output" through the replay path (so every plot pane sees them).
- **A record is chosen by id.** History's per-row "analyse" emits `analysis:record`; the Analysis widget
  selects it (refreshing its list if the record is newer than the list). The picker is the second way,
  for when History is not open. A plot pane's pinned record is not a third way yet: the id is on the bus
  already (`plot:view`), so a "from Plot N" choice is a small later addition.
- **Tune-up widget** (`widgets/tuneup.ts`): the nodes, the run options (its own field since ADR 0056), start
  and stop, the DAG state from `TuneUp` (`tuneupLines` moved with it, still pure). A finished tune-up emits
  `records:changed`, as a finished run does, so History and Analysis refresh.
- **`panel.ts` and the `control` widget are deleted.** No `#`-ids remain in form widgets; the e2e tests
  address every widget by `.pane[data-widget=…]` and class or `data-*` hooks. Default layout: sweep +
  analysis + tune-up | plot | pulse + levels + history, under `flightdeck.layout.v4`.
- Deliverable 6 (the Script widget placeholder) is the last; it does not touch this.

## Consequences
- Easier: every former panel capability is a widget the user can place, close or duplicate (within the
  single-instance rule); the analysis form no longer competes with the sweep form for the same pane.
- Harder: an analysis needs History or the picker to name a record (one more click than the old inline
  list); two widgets each refresh records after a run (cheap, but two requests).
- Exit criterion "`panel.ts` is gone; every former panel capability exists as a widget; all e2e green" met.

## Alternatives considered
- Keep the records list inside the Analysis widget — rejected: History is the records browser (ADR 0055);
  a second list would drift.
- Analyse the record a plot pane is pinned to, implicitly — deferred: explicit is better when several panes
  show records; the hook exists.
