# 0012 — Flight Deck v0 architecture: one decoder, raw WebGL2, cross-language oracles

**Status:** Accepted (renderer library provisional until the #9 benchmark)
**Date:** 2026-10-11
**Step:** 1

## Context
ADR 0008 fixed WebGL for the 2D view and left the library (Open Decision #9) to a Step 1 benchmark. ADR
0011 allowed UI work against the drafted contract. Flight Deck must be source-agnostic (rule 8, ADR 0005),
prove source equivalence, and render the 2048² design target live. There is no GL context in CI's Node
test environment.

## Decision
Every Flight Deck source yields raw ADR 0010 wire messages, and one shared `Decoder` turns them into
events. Sources differ only in transport. Correctness is pinned by cross-language content oracles: sha256
of each array as assembled by the Python reference consumer, committed beside each `.qdtrec` fixture. The
v0 2D renderer is raw WebGL2 with no library. A CPU reference renderer that shares the colormap formula
serves as the snapshot oracle and as the no-WebGL2 fallback. The view is chosen from the Dataset's shape only.

## Consequences
- Easier: source equivalence holds by construction and is tested three ways (replay, a WebSocket replaying
  the same bytes, the real Python server). Decoder bugs show up as hash mismatches against Python, not as
  visual differences. Raw WebGL2 has no dependency and keeps live updates to `texSubImage2D` per dirty row.
- Harder: GPU output is not pixel-tested in CI; only the CPU path is snapshotted. GPU and CPU colours agree
  by construction (same polynomial), not by test. Raw WebGL2 means writing axes, zoom and cursors ourselves
  if no library is adopted.
- Must now: the #9 benchmark compares this raw-WebGL2 baseline against candidate libraries at 2048² and
  10⁶ pts/s in a real browser (headless Chrome works locally: `--use-angle=swiftshader`), then records the
  choice. A browser-based pixel/latency test belongs with that benchmark. Regenerate the oracles with the
  fixtures (`scripts/make_stream_fixtures.py`).
- pnpm is pinned through `packageManager` and run via corepack; no global install.

## Alternatives considered
- Per-source decoding paths — rejected: equivalence would be a property to test rather than a construction.
- Comparing Flight Deck output to Python by re-rendering in Python — rejected: compares two renderers;
  hashing the assembled arrays compares the contract.
- Picking a WebGL library now (regl, deck.gl, a WebGL plotting lib) — deferred to the #9 benchmark; raw
  WebGL2 is the baseline every candidate must beat on ergonomics without losing throughput.
- jsdom/headless-gl in Vitest for GPU snapshots — rejected for v0: brittle native deps on Windows/CI;
  real-browser testing goes with the benchmark.
