# Analysis 0001 — Dataset stream budget: transport, encoding, renderer class

**Date:** 2026-10-11 · **Informs:** ADR 0008 · **Step:** 1
**Kind:** analysis note. Not a decision. ADRs cite analyses; analyses never contain decisions.

## Question
Plan Open Decisions #8 (stream transport) and #9 (Flight Deck stack) were gated on measuring the largest
2D map and the fastest OPX chunk rate. Can these be decided from first principles with margin, and if so,
what is the probe still for?

## Design targets (ceiling of plausible dot-tuning need)
| Target | Value | Rationale |
|---|---|---|
| Largest 2D map | 2048 × 2048, float32 | ~4× linear over a typical high-resolution stability diagram (≤ 1000²) |
| Sustained stream rate | 10⁶ points/s | ~10× over practical OPX processed-result rates (see §5) |
| Live-mode latency | ≤ 50 ms glass-to-glass | below the threshold at which a live map feels laggy during gate sweeps |

These three numbers are the contract the synthetic source and the L0 throughput test are built against.
They go into `docs/FINISH_LINE.md`.

## 1. Bytes
- Full frame: 2048² × 4 B = 16.8 MB.
- One line: 2048 × 4 B = 8 KB.
- Stream at 10⁶ points/s: 4 MB/s.
- Localhost WebSocket: hundreds of MB/s. Gigabit LAN: 125 MB/s.

**Transport throughput is not a constraint by > 1 order of magnitude at the ceiling target.**

## 2. Encoding (the real decision)
| Encoding | Bytes/float | Decode cost (browser) | 4M-point frame |
|---|---|---|---|
| JSON number | ~10–12 | ~1 µs/number (parse + boxing) | ~50 MB text, ~1 s parse |
| Arrow IPC / raw typed-array buffer | 4 | zero-copy into `Float32Array` | 16.8 MB, ~0 ms |

JSON for the array payload fails the latency target by ~20× at the ceiling and by ~2× even at a 500²
map. **Binary array chunks are required by arithmetic.** A small JSON envelope for metadata and
`Annotation`s is fine: metadata is O(1) per chunk, not O(points).

Among binary options in a browser: gRPC-web does not support true bidirectional streaming; Arrow Flight is
not browser-native. WebSocket carries binary frames natively and bidirectionally (needed later for the
single "up" edge — click-to-set). **WebSocket + Arrow IPC** is the only option that satisfies every
constraint without a browser shim.

## 3. Rendering
- Full-frame GPU texture upload: 16.8 MB. At 10 full refreshes/s: 168 MB/s — within integrated-GPU budget.
- Line update via `texSubImage2D`: 8 KB per line; negligible.
- Canvas-2D heatmap redraw: ~10⁶ points is marginal (tens of ms per redraw on a laptop).
- SVG / DOM-based plotting (Plotly, D3 marks): unusable above ~10⁵ points.

**The 2D view must be WebGL from the start.** Which WebGL library (regl, deck.gl, custom shader, a
WebGL-backed plotting lib) is a taste/ergonomics question; the Step 1 benchmark is a tie-breaker, not a gate.
1D traces can be canvas-2D (≤ 10⁴ points is trivially fast).

## 4. Latency budget (50 ms target, live line-wise update)
| Stage | Estimate |
|---|---|
| Producer → stream server (in-process) | < 1 ms |
| WebSocket hop (localhost / LAN) | < 1 ms / ~1 ms |
| Arrow decode | ~0 |
| `texSubImage2D` + draw | ≤ 16 ms (one frame at 60 Hz) |
| **Total** | **≈ 20 ms**, leaving ~30 ms headroom for the OPX fetch cadence itself |

The dominant term is therefore the producer's own cadence (how often the OPX result handle yields new
points), not anything in the toolkit. This is a semantic question — see §6.

## 5. OPX reality check
The OPX streams *processed* results (demodulated/integrated values, stream-processed buffers), not raw ADC,
except in short bursts. Sustained rates for processed points are typically 10⁴–10⁵/s in practice, so the
10⁶ target carries roughly an order of magnitude of margin. A benchtop scope is pull-based: one full record
per query (`:WAV:DATA?`), typically 10³–10⁶ samples at a few Hz. Both fit comfortably inside the budget.
If the probe shows higher rates, only the margin moves; no decision in this note changes.

## 6. What remains unknown (and is worth a probe)
Everything above is *size*. The contract's hard parts are *shape*:
1. **Delivery granularity** — does a result arrive per point, per line (`buffer(n)`), or per frame (`buffer(n, m)`)? Can a partial buffer be fetched mid-acquisition?
2. **Coordinate addressing** — OPX results are positional (indexed by loop order); coordinates are implied by the sweep definition, not carried in-band. The scope carries its own time axis. `DatasetChunk` must support both *implicit-from-definition* and *explicit* coordinates.
3. **In-band metadata** — what, if anything, rides with the data (timestamps via a timestamp stream; nothing else). Everything else must come from the executor.
4. **Push vs pull** — OPX result handles are polled; scope is polled; neither pushes. The stream server is therefore a poller that converts to push; the cadence it can sustain is the probe's one quantitative output.
5. **QUA constraints** — what a compiled inner loop can and cannot vary without recompilation (affects `SweepDefinition`'s payload slot).

These five items are the scope of `docs/probes/01-stream-semantics.md`.

## Conclusion
#8 and the renderer class of #9 are decidable now. The probe narrows to semantics and one cadence
measurement, and is the gate for *freezing* the contract, not for *drafting* it.
