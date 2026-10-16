# 0055 — Plot panes: any number over the shared stores, each following the stream or pinned to a record; six at most

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 6b (deliverable 2; extends 0054)

## Context
ADR 0054 made the centre column a stack of plot panes but the shell (session 1) shipped one: the Step 1–6
stage with its header selects, single-instance so the e2e ids kept working. The workspace exists to show a
live map beside a stored one (FINISH_LINE: compare across cooldowns), so the pane has to multiply, each
with its own view, over the one set of Dataset stores. Three questions follow: how a pane chooses what it
shows, how a stored record reaches a pane, and how many panes a page can hold when each owns a WebGL2
context (browsers allow 8–16 per page, then the oldest is lost).

## Decision
- **One `Datasets` collection, N panes.** Every pane reads the same stores (`src/stream/datasets.ts`); a
  pane never copies data. Each pane owns its `MapRenderer`, its view options (variable, minus, transform,
  swap) and its line cut, in memory; the layout persists which panes exist, not what they show.
- **Follow or pin.** A pane either *follows* the stream (shows the newest Dataset as it arrives; the
  default, and what a split pane does) or is *pinned* to one Dataset chosen in its ⚙ menu. Only following
  panes report `stream:state` to the strip, so the strip's live pill, telemetry and progress describe the
  stream, never a pinned record.
- **A record opens through the replay stream.** History asks the server to replay the record
  (`POST /stream/replay`, the path the panel's "show" already used) and tells a pane `plot:open`; the pane
  pins itself to the Dataset that *is* the record, now if it is on the stream already or when it arrives.
  Two ids name it: `source.registry_ref` (a replay, ADR 0027) or the Dataset id equal to the record's
  `plan_id` (the run that made it is still on the stream; the server then publishes only its overlays and
  announces nothing). The registry-ref read is the one permitted read of `.source` and stays display-only:
  the pane matches ids, it never branches on a producer. Panes announce what they show (`plot:view`) so
  History can list "shown in".
- **Six plot panes at most** (`MAX_PLOT_PANES`): the layout refuses a seventh split; a closed pane
  disposes its renderer (`WEBGL_lose_context`). `defaultMapRenderer` already falls back to the CPU path
  when a context cannot be created, so an exhausted browser degrades rather than breaks. This closes the
  step's "WebGL2 context cap" open decision.
- **Click stays click-to-set.** A click on the map offers the point as a setpoint (ADR 0053); the cut's
  position comes from the ⚙ menu's slider, drawn as a dashed rule on the overlay and a trace strip under
  the map. The prototype's click-to-cut gave way to the one "up" edge.
- **The ⚙ menu is the pane's header.** Dataset, variable, minus, transform, swap axes, cut. It is
  focus-trapped and closes on Escape (returning focus to ⚙) or on a click outside. Colormap is not in it
  yet: the renderers share one viridis formula (shader and CPU oracle); a second colormap is a renderer
  change with pixel tests, its own slice.
- **Source equivalence across panes** is a pure-layer test: the full display map (stack mean, transform,
  swap) is one function (`render/display.ts`) and two panes over the same store produce byte-identical maps
  and images.

## Consequences
- Easier: live beside a record, two records side by side, each with its own derivative or swap; History
  is a widget with "open in Plot N / a new pane"; the e2e tests drive panes by position and menu, not ids.
- Harder: the strip shows one stream state when several panes follow (they agree; the newest reporter
  wins); view state does not survive a reload (a `view` field on the persisted pane is an additive change
  when wanted); the cap is a constant, not a probe of the browser.
- The panel's Records list and "show" button duplicate History until deliverable 5 deletes the panel.

## Alternatives considered
- Fetch a record's payload over HTTP into a pane (no replay) — rejected: a second data path beside the
  stream, and overlays would need their own; the stream already carries both (ADR 0032).
- Share one WebGL2 context across panes (one canvas, viewports) — rejected for now: every pane's renderer
  would couple through one context and the pixel oracle; the cap keeps the per-pane renderer the bench
  measured. Revisit if six is not enough.
- Click-to-cut as in the prototype — rejected: the click is the stand's one "up" edge (ADR 0053).
