# 0013 — Flight Deck 2D renderer: raw WebGL2, no library (closes Open Decision #9)

**Status:** Accepted
**Date:** 2026-10-11
**Step:** 1
**Analysis:** `docs/analysis/0002-renderer-benchmark.md`

## Context
ADR 0008 chose WebGL for the 2D view. It left the library (Open Decision #9) to a Step 1 benchmark acting
as tie-breaker. ADR 0012 made raw WebGL2 the baseline. Analysis 0002 benchmarked three renderers live
against the Python stream server at the design targets, on a discrete GPU and on SwiftShader:
- raw WebGL2;
- regl, the thinnest mainstream WebGL library and the one closest to the needed design (float texture,
  sub-image row updates, shader colormap);
- canvas-2D.

## Decision
Use raw WebGL2 for the Flight Deck 2D view, with no rendering library, and remove the regl candidate. Keep
the canvas-2D renderer only as the no-WebGL2 fallback and test reference. Keep the CI benchmark assertion
(2048², 10⁶ points/s, steady-state p95 ≤ 50 ms on SwiftShader) as the regression guard for this choice.

## Consequences
- Easier: no rendering dependency (bundle 196 KB against 319 KB with regl); native WebGL2 float textures
  and `isnan`; one renderer interface with a pixel-tested GPU path and a CPU oracle.
- Harder: axes, colorbar, cursors, line cuts and zoom are written by hand (canvas-2D overlays on the
  WebGL canvas), since no plotting library provides them.
- Must now: keep `bench/run.mjs --assert` and `pnpm test:e2e` in CI. Re-run the benchmark on the bench
  laptop at Step 5, and with point-wise chunks if Probe 01 shows the OPX delivers per point.
- Open Decision #9 is closed. The live-rendering exit criterion is met on the development machine and
  asserted in CI.

## Alternatives considered
- regl — rejected: equal throughput and latency (Analysis 0002), but WebGL1-only, extension-dependent float
  textures, and +123 KB, with nothing gained on the axis of the decision.
- deck.gl / luma.gl — not benchmarked: a geospatial framework whose float-texture bitmap path needs custom
  layers, so it would add weight for capabilities Flight Deck does not use. Revisit only if multi-layer
  composition becomes a requirement.
- A WebGL plotting library (line/scatter oriented) — rejected: none offers live float-texture heatmaps with
  per-row updates. We would wrap our own shader anyway.
- Canvas-2D as the primary renderer — rejected by measurement: steady-state p95 ~240 ms at the targets.
