# 0054 — Flight Deck is a workspace of widgets: three columns, plots only in the centre, one Run

**Status:** Proposed
**Date:** 2026-10-15
**Step:** 6b

## Context
Flight Deck today is one stage canvas beside one 850-line control panel (`control/panel.ts`), which has
absorbed sweeps, sequences, levels, methods, records and the tune-up runner as they arrived. The human
iterated a layout prototype on 2026-10-15 (`docs/examples/flightdeck-workspace-proto.html`) and settled
the shape: the plot is the hero and lives in the centre; editors and browsers are widgets in resizable,
splittable side columns; one Run action in the top strip; per-pane settings in a corner menu; telemetry
in the strip; history is a widget, not a plot side-bar. The pure form models (`control/sweeps.ts`,
`control/sequence.ts`, `control/methods.ts`) are already unit-tested and framework-free; only presentation
needs to change. Rule 8 and the generated-types rules are unaffected.

## Decision
- **Layout model.** `Layout = { left: Pane[], center: PlotPane[], right: Pane[], widths }`,
  `Pane = { id, widget, size }`. Columns are vertical stacks; no nested horizontal splits. Panes split
  below and close; a split is refused below a minimum pane height. Layout is UI state persisted per
  browser (localStorage, try/catch-guarded), exportable as JSON; it is not a schema object.
- **Widget contract.** `Widget = { id, label, sub, mount(host, head, ctx) => unmount }`. `ctx` gives the
  `ApiClient`, the shared `DatasetStore`, a typed event bus (run started/finished, record stored, stand
  changed, open-record-in-pane), and layout operations (add a plot pane). Widgets talk to the server only
  through `ApiClient` and never import a driver. A widget owns no cross-widget state; shared state lives in
  the store or travels on the bus.
- **Plot panes.** Any number, centre only, each with its own renderer, view options and cut; each either
  follows the live stream or is pinned to a dataset. The ⚙ menu holds what the old header selects did.
- **One Run.** The strip's Run binds to the last compiled `ExecutionPlan`; the strip shows the plan's
  identity and a stale marker when an editor changes after compile. Editors never run.
- **Decomposition.** `panel.ts` is extracted into widgets one session at a time (sweep, pulse, levels,
  virtual gates, history, methods, tune-up), with the first session mounting it unchanged as a temporary
  widget so the shell lands without a behaviour change. `panel.ts` is deleted when the last widget lands.
- **Visual system is data.** A theme is a JSON file (`apps/flightdeck/themes/*.json`, `theme.schema.json`):
  thirteen colour tokens, type, shape, `scheme`, and a closed allow-list of decoration flags that enable
  stylesheet classes. Built-ins: `slate` (Plex Sans, one amber accent for live state), `paper` (light), `steel`
  (near-black, hairlines, corner brackets, graticule, tracked caps, one signal colour). Users load and export
  themes; a theme can never inject CSS. Colormaps are view settings, not theme content.

## Consequences
- Easier: several maps at once (live beside a cooldown reference); widgets added without touching the
  shell; `main.ts` becomes wiring; e2e tests target widgets rather than one monolith.
- Harder: N WebGL2 contexts (cap or cpu fallback); per-pane view state must be reset/cleaned on close;
  a decoration flag is a permanent public contract once a theme file in the wild uses it;
  the stale-plan marker needs the compile response's identity surfaced by `qdt-server`.
- Must now: `GET /levels` with readbacks on `qdt-server` for the operating-point widget (own ADR when
  built); mount/unmount symmetry tested so closed panes leak nothing.

## Alternatives considered
- Dockable tiling with nested splits — rejected: the three-column shape encodes prepare/observe/inspect
  and keeps two gutter kinds; nested grids lose both.
- A UI framework (React/Svelte) for the widget layer — rejected for now: the existing code is framework-free
  and generated-type driven; the widget contract is small enough in plain TS. Revisit if widget count
  makes manual DOM untenable.
- Layout as a schema object from the start — rejected: UI state, single user; promote only if shared.
