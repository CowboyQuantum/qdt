# 0061 — Flight Deck follow-ups: colormaps as a view setting shared by both renderers, a pane remembers its view, web fonts opt-in, a run queue in the UI, tune-up coefficients offered to the coupling matrix, the record a plot shows is analysable

**Status:** Accepted
**Date:** 2026-10-16
**Step:** after 6b (extends 0054–0058)

## Context
Step 6b closed with six small things listed as "not yet real" in STATUS. Each is a one-screen decision; the
human asked to clear them up together (2026-10-16). None touches a schema.

## Decision
- **Colormaps are a per-pane view setting**, not theme content (ADR 0054 said so). Three: `viridis`,
  `magma`, `grey`. Viridis keeps its polynomial, the same formula in the shader and the CPU oracle (ADR
  0013). The others are anchor tables sampled into a 256-entry LUT that both renderers read the same
  way: the GPU as a LINEAR 256×1 texture sampled at entry centres, the CPU by the same linear
  interpolation between entries. So the pixel test (every renderer × every colormap against the CPU
  reference, within two levels) keeps the CPU path an oracle for the GPU path. Magma's anchors are nine
  evenly spaced samples of matplotlib's table, linear between them: close, not the reference curve.
- **A pane remembers its view across a reload.** `Pane.state` (opaque to the layout) is persisted with
  the layout; a widget gets it on mount (`ctx.pane.state`) and saves it (`ctx.pane.save`). The plot
  stores variable, minus, transform, swap, cut and colormap, never a dataset id: the stream is new each
  time, so a pane that was pinned comes back following. State goes when the pane takes another widget.
- **Web fonts are a per-browser opt-in**, off by default (`flightdeck.webfonts.v1`, a checkbox in the
  theme menu): a bench is offline and the Plex stacks fall back to system fonts; online, the link to
  Google Fonts is injected. A theme never names a URL.
- **The UI queues runs.** The server already executes runs one at a time behind a lock and holds the
  rest as `queued`; the Sweep widget follows every run it started and no longer refuses Run while one is
  live. The strip shows the run executing (else the latest) and how many wait; abort takes the running
  one, else the newest queued.
- **A tune-up's virtual-gate coefficients are offered, never applied unasked.** When a tune-up ends with
  an accepted node whose outputs carry `c_21`/`c_12` (ADR 0049), the Tune-up widget names the gates (the
  node's outer axis channel and its inner pulse channel without `_pulse`) and the Virtual gates widget
  shows one "apply" button with the values; applying writes row g1 → g2 = `c_21`, row g2 → g1 = `c_12`.
- **The record a plot pane shows is a choice in the Analysis picker** ("shown in a plot: Plot N · …"),
  from what panes announce (`plot:view`); History's "analyse" and the stored list remain.

## Consequences
- Easier: a stored record and the live map side by side in different colormaps; a reload keeps the
  workspace as left; a tune-up's result is one click from a virtual-gate sweep.
- Harder: a second colormap family (diverging, for a derivative) is anchors in one file; a request for
  the reference magma means a fit like viridis's. A run queue in the UI has no reordering: the server
  has none.

## Alternatives considered
- A colormap LUT for viridis too — rejected: the polynomial is the pixel oracle's contract (ADR 0013) and
  the committed snapshot; one more code path is cheaper than a changed oracle.
- Persisting the pinned dataset id — rejected: ids are per stream; a stale pin would be a lie.
- Loading web fonts always — rejected: the bench is offline (STATUS said so twice).
