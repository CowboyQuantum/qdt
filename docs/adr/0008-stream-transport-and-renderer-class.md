# 0008 — Stream transport, encoding, and renderer class

**Status:** Accepted
**Date:** 2026-10-11
**Step:** 1
**Analysis:** `docs/analysis/0001-stream-budget.md`

## Context
Open Decisions #8 and #9 were gated on measuring map size and OPX chunk rate. Analysis 0001 shows the
decision is determined by arithmetic at ceiling design targets (2048² float32, 10⁶ points/s, ≤ 50 ms),
and that the genuine unknowns are chunk semantics, not sizes.

## Decision
`Dataset` chunks are carried over WebSocket as Arrow IPC binary frames with a small JSON envelope for
metadata and `Annotation`s. Flight Deck's 2D view is WebGL from the start; 1D views may use canvas-2D.
The three design targets are written into `docs/FINISH_LINE.md` and define the synthetic source and the
L0 throughput test. The Step 1 probe is narrowed to stream semantics and one cadence measurement
(`docs/probes/01-stream-semantics.md`) and gates the contract *freeze*, not the contract *draft*.
Open Decision #8 is closed; #9 is reduced to library choice, settled by the Step 1 benchmark as a tie-breaker.

## Consequences
- Easier: Step 1 contract drafting starts without lab time; the synthetic source has concrete numbers to emulate.
- Harder: WebGL raises the floor on front-end complexity; JSON-only debugging of the stream is not possible (add a `--debug-json` sidecar if needed).
- Must now: run the semantics probe before the freeze ADR; keep the three targets in FINISH_LINE.md current.

## Alternatives considered
- JSON array payloads — rejected by arithmetic (≈1 s parse per ceiling frame).
- gRPC-web / Arrow Flight — rejected: no native bidirectional browser streaming / not browser-native.
- Canvas-2D or Plotly-class 2D rendering — rejected: fails interactive rates above ~10⁵–10⁶ points.
- Keep the measurement gate as originally framed — rejected: the sizes are boundable; only the shape is not.
