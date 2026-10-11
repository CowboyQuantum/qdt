# Analysis 0002 — Flight Deck 2D renderer benchmark

**Date:** 2026-10-11 · **Informs:** ADR 0013 · **Step:** 1
**Kind:** analysis note. Not a decision. ADRs cite analyses; analyses never contain decisions.

## Question
Open Decision #9 was reduced by ADR 0008 to choosing a WebGL library for the 2D view, with the Step 1
benchmark as tie-breaker. Does any candidate beat the raw-WebGL2 baseline (ADR 0012)? Do the Analysis 0001
targets hold live, end to end: 2048² float32, 10⁶ points/s, ≤ 50 ms?

## Method
`apps/flightdeck/bench/run.mjs` (code at `d9909b3`, which still contains the regl candidate):
- **Producer:** `python -m qdt_lab.stream --size 2048 --rate 1000000 --wait-for-client`. This is the
  synthetic map, one 2048-point line per chunk, paced at 10⁶ points/s.
- **Consumer:** the built Flight Deck in headless system Chrome 154, driven by `playwright-core`, with
  `?bench=1&renderer=…`.
- **Latency:** per chunk, `drawn − produced_at`. `produced_at` is the producer's stamp. `drawn` is
  `Date.now()` after the frame's GPU work completes (a 1-pixel readback forces the sync). Both use the same
  machine clock. The figure includes the wait for the next `requestAnimationFrame`.
- **Steady state:** chunks produced after the first 500 ms. That excludes first-frame texture allocation
  and shader compile.
- **Rendered rate:** total points ÷ (last chunk drawn − first chunk produced).
- **Hardware:** Windows 11, NVIDIA RTX 4090, ANGLE/D3D11, vsync-locked at ~60 fps. Also SwiftShader
  (software Vulkan), which is what a GPU-less CI runner gets.

Raw results: `apps/flightdeck/bench/results/2026-10-11-{hardware,swiftshader}.json`.

## Results (2048², 10⁶ points/s, 2048 chunks)

| GPU | Renderer | p50 | p95 | p99 | max | steady p95 / max | rendered pts/s | frames |
|---|---|---|---|---|---|---|---|---|
| RTX 4090 | raw WebGL2 | 10 | 18 | 54 | 95 | 17 / 18 | 999,834 | 248 |
| RTX 4090 | regl (WebGL1) | 10 | 18 | 58 | 90 | 18 / 19 | 999,596 | 249 |
| RTX 4090 | canvas-2D (CPU) | 16 | 236 | 332 | 373 | 242 / 373 | 996,508 | 196 |
| SwiftShader | raw WebGL2 | 7 | 115 | 256 | 290 | 11 / 13 | 999,834 | 471 |
| SwiftShader | regl (WebGL1) | 7 | 11 | 41 | 74 | 10 / 13 | 998,644 | 497 |
| SwiftShader | canvas-2D (CPU) | 10 | 186 | 241 | 272 | 193 / 272 | 999,120 | 375 |

All latencies are in ms.

## Observations
1. **Both WebGL paths meet the 50 ms target in steady state with ~3× margin and keep up with the
   producer.** They are indistinguishable from each other within run-to-run noise (repeat runs moved p99
   by ±5 ms).
2. **Every chunk over target falls in the first ~10 ms of the stream** (the "worst at" times in the raw
   output). It is a one-off start-up cost: 2048² texture allocation plus shader compile, ~100 ms on the GPU
   and up to ~290 ms for WebGL2's R32F allocation in software. regl's smaller start-up spike on SwiftShader
   comes from its WebGL1 luminance texture path. It is not a steady-state difference.
3. **Canvas-2D fails by ~5×.** The live colour range widens as new rows arrive, and each widening re-maps
   the full 4M-point image on the CPU. This is Analysis 0001 §3's prediction, now measured.
4. **Latency is dominated by frame cadence, not by data handling.** Vsync-locked hardware (~60 fps) shows
   higher steady latency than unthrottled SwiftShader (~110 fps). The data path itself (decode, row
   upload, draw) fits well inside one frame.
5. **Bundle size:** 196 KB without regl, 319 KB with it. regl targets WebGL1, so float textures need
   `OES_texture_float` and the shader has no `isnan` (it uses `v != v`).

## What remains unmeasured
- **First-frame latency:** a future step could pre-allocate the texture when the Dataset is announced,
  before the first chunk arrives.
- **Display hardware:** integrated GPUs and the bench laptop (Step 5). The CI assertion runs on SwiftShader,
  which this note shows is not slower in steady state.
- **Point-wise chunks:** Probe 01 may show the OPX delivers per point. That would mean ~500k chunks/s at
  this rate, a decode-bound regime this run does not exercise. `bench/run.mjs --points-per-chunk` exists
  for that follow-up.
