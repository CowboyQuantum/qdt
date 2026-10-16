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
- WebGL2 context cap: browsers allow ~8–16 contexts; cap plot panes (e.g. 6) or fall back to `cpu` beyond it.
- `GET /levels` readback semantics when a channel has no `LevelSense` (null vs. omitted).
- Script sandbox (server-side execution of restricted measurement scripts) — separate ADR.
- Which widgets appear in the release mirror's first public build.
- Whether uploaded themes are shared through the registry (a `Theme` record) or stay per browser. Default: per browser.

## Status
NOT STARTED
