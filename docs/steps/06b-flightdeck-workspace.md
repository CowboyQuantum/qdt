# Step 6b — Flight Deck workspace

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.
> Design reference: `docs/examples/flightdeck-workspace-proto.html` (interactive prototype, 2026-10-15) and
> `docs/examples/flightdeck-theme-ember.json` (an example theme file).
> Reference only — nothing is imported from it; it shows the intended shape and interactions.

## Goal
Flight Deck becomes a workspace: three columns, each a vertical stack of panes. The centre column holds
only plot panes (any number); the side columns host editor and browser widgets. One Run action in the top
strip. Per-pane view settings in a corner menu. The 850-line control panel is decomposed into widgets with
no change to the pure form models it is built on. Interleaves with Step 6; starts after click-to-set lands.

## Schema slice
None. Layout is UI state (per browser), not a schema object — see ADR 0054 and Open decisions.

## Deliverables
Ordered; one session each.
1. **Shell.** Themes as data: `apps/flightdeck/themes/*.json` (built-ins `slate`, `paper`, `steel`) validated
   against `theme.schema.json` — thirteen `#rrggbb` tokens, type (sans/mono/size), shape (radii), `scheme`,
   and a closed allow-list of decoration `flags` (`caps`, `brackets`, `graticule`, `glow`, `flat`) that switch
   stylesheet classes on; a theme can never inject CSS. Theme menu with load-from-file, export, and per-browser
   persistence. Colormaps are *not* theme content (a theme may set a default; a plot pane overrides). Top strip (stand, device, source,
   live pill, next-run summary, Run, stream telemetry + progress), workspace with the layout model
   (`src/workspace/layout.ts`: columns of panes, split/close/resize, min pane height, persistence), widget
   registry and contract (`src/workspace/widget.ts`), event bus (`src/workspace/bus.ts`). The existing
   `ControlPanel` is mounted unchanged as a single temporary `control` widget in the left column; the single
   stage becomes the first centre plot pane. No behaviour change; `main.ts` shrinks to wiring.
2. **Plot panes.** `src/widgets/plot.ts`: N instances over the shared `DatasetStore`, each with its own
   `MapRenderer`, view options and cut cursor; header ⚙ menu holds dataset/variable/minus/transform/swap/
   colormap/cut. A pane either follows live or is pinned to a dataset. WebGL2 context cap (see Open decisions).
   `src/widgets/history.ts`: records from `/records`, search, "shown in", open-in-plot (existing pane or new).
3. **Sweep + Pulse widgets** extracted from `panel.ts` over `control/sweeps.ts` and `control/sequence.ts`
   unchanged. Run moves to the strip and binds to the *compiled plan*: the strip shows the plan's identity
   from the compile response and marks it stale when an editor changes after compile.
4. **Levels (operating point) widget** over ADR 0038's fixed levels: filterable (type, instrument, text,
   pinned, near-limit; AND across groups, OR within), sortable, pinnable, inline set with limit refusal and
   settling state. Needs readbacks: `GET /levels` on `qdt-server` returning setpoint + `LevelSense` readback
   per channel where the stand declares one (ADR). **Virtual gates widget** over ADR 0049 couplings.
5. **Methods + tune-up widgets** extracted; `panel.ts` deleted; `e2e/control.test.ts` migrated to the
   widget workspace.
6. **Script widget** as a placeholder (allowed-API panel, stage button that only validates). A real
   server-side sandbox is its own ADR, not this step.

## L0 tests (CI)
- `layout.test.ts`: split/close/resize invariants, sizes sum, min-height refusal, persistence round trip.
- `widget.test.ts`: registry, mount/unmount symmetry (no leaked listeners or contexts), bus typing.
- `render.test.ts` extended: the same Dataset in two plot panes renders identically (source-equivalence
  across panes); rule-8 import test unchanged.
- `pixels.test.ts` extended: default workspace snapshot; centre split with live + record side by side.
- `control.test.ts` migrated: compile → Run from strip → record in History → open in Plot 2 → overlay.
- a11y smoke: gutters resize from the keyboard; ⚙ menu is focus-trapped and closes on Escape.

## L1 tests (bench loopback)
- none (UI); Step 5 drivers already stream through the same source.

## L2 tests (instrument-on-instrument)
- none

## Exit criteria
- `panel.ts` is gone; every former panel capability exists as a widget; all e2e green.
- Two plot panes show live and a stored record simultaneously with independent cuts.
- Exactly one Run control, bound to a compiled plan with a visible identity and stale marker.
- Layout persists and restores; `+` refuses below the min pane height.

## Open decisions
- Layout as a schema object (shareable workspaces through the registry) — deferred; revisit if a second
  user needs the same workspace.
- ~~WebGL2 context cap~~ — closed by ADR 0055: six plot panes at most; a closed pane loses its context; the CPU renderer is the fallback when a context cannot be made.
- `GET /levels` readback semantics when a channel has no `LevelSense` (null vs. omitted).
- Script sandbox (server-side execution of restricted measurement scripts) — separate ADR.
- Which widgets appear in the release mirror's first public build.
- Whether uploaded themes are shared through the registry (a `Theme` record) or stay per browser. Default: per browser.

## Status
IN PROGRESS (opened 2026-10-15 on the human's "go with 6b"; ADR 0054 accepted with it).
Session 1 (2026-10-15): **the shell** (deliverable 1). Themes as data: `themes/{slate,paper,steel}.json`,
`theme.schema.json`, `workspace/theme.ts` (validator, `themeStyle`, `applyTheme`, `ThemeManager` with
load/export/per-browser persistence; the schema and the validator are held in step by a test; no Google Fonts
link, the Plex stacks fall back to system fonts at an offline bench). The strip (`workspace/strip.ts`): stand and
device from the API, source, live pill, next-run line, Run (submits the control panel's form through the bus),
telemetry (`#status`), progress, messages, replay picker, theme menu. The layout model (`workspace/layout.ts`,
pure; split refused below `MIN_PANE_HEIGHT`, close keeps a column's last pane, sizes normalised, widths clamped,
`flightdeck.layout.v1` in localStorage behind try/catch), the widget contract and registry (`workspace/widget.ts`;
a bus scoped per mount is disposed on unmount), the typed bus (`workspace/bus.ts`), the renderer
(`workspace/workspace.ts`: panes reconciled by id, pointer and keyboard gutters). Widgets: `plot` (the old stage,
one instance, its selects in the pane head; emits `stream:state` and `map:click`), `control` (the Step 4b panel
unchanged; listens for `run:request` and `map:click`), `empty`. `main.ts` is 60 lines of wiring. No behaviour
change: the six Step 4b–6 e2e tests pass untouched; `e2e/workspace.test.ts` (3) covers the default layout, the
theme on `:root`, split/close/persist, the keyboard gutters and the theme menu; 28 unit tests for layout, widget,
bus and theme. Left for deliverable 2: N plot panes (the centre's `+` is disabled while `plot` is single), the
⚙ menu, history; the WebGL2 context cap (Open decisions).
Session 2 (2026-10-15): **plot panes and History** (deliverable 2, ADR 0055). `plot` is N centre panes over the
shared `Datasets`, each with its own `MapRenderer` (disposed on close), view options and line cut; a pane follows
the stream or is pinned to one Dataset from its ⚙ menu (dataset, variable, minus, transform, swap, cut;
focus-trapped, Escape closes); only following panes drive the strip. `history` (`src/widgets/history.ts`) lists
`/records`, searches, shows "shown in" from what panes announce (`plot:view`), and opens a record in an existing
or new pane: the server replays it and the pane pins itself to the Dataset that is the record (registry ref, or
the record's plan id when its run is still on the stream). Six panes at most (`MAX_PLOT_PANES`; closes the
WebGL2 context cap decision). The full display map is one pure function (`render/display.ts`); two panes over
one store are byte-identical (`render.test.ts`). The e2e tests address panes by position and menu, never by id;
`control.test.ts` opens the run's record from History into Plot 2 while Plot 1 follows live. Not done: colormap
in the menu (one viridis formula shared by shader and oracle; a renderer slice of its own); per-pane view state
across a reload. Next: deliverable 3, the Sweep and Pulse widgets with Run bound to the compiled plan.
