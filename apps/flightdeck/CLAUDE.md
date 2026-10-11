# apps/flightdeck — package rules

Flight Deck is the front end. Restarted from scratch (ADR 0005). TypeScript. Transport and renderer class are decided (ADR 0008): WebSocket + Arrow IPC, WebGL 2D. The 2D renderer is raw WebGL2 with no library (ADR 0013, closing #9); `pnpm bench` reproduces Analysis 0002 and `--assert` guards the targets in CI. Browser pixel tests: `pnpm build && pnpm test:e2e`.

## Entry gate (ADR 0011)
UI code may be written once `docs/FINISH_LINE.md` is authored (done) and the `Dataset` stream contract is **drafted** in `qdt-schemas` with ADRs (done: ADR 0009, 0010). The contract *freeze* (after Probe 01) gates Step 1's exit, not UI work. Until the freeze:
- consume only the generated types and the wire protocol of ADR 0010; never hand-code around a draft field;
- a contract change regenerates `src/schema/` and must keep every Flight Deck test green in the same commit.

## Rules
- Rule 8: never import an instrument driver; never branch on which instrument produced a `Dataset`. `scripts/check_imports.py` greps for violations.
- All data enters through a `Source` implementation (`replay`, `websocket`, later `registry`). A new source must pass the source-equivalence test: the same `Dataset` through any source renders identically.
- Types under `src/schema/` are **generated** from `packages/qdt-schemas/exports/jsonschema/data.schema.json` (`pnpm gen:types`); CI fails on drift. Never edit them by hand.
- Transforms (derivative, filter, normalize) are client-side on typed arrays; no server round-trip per toggle.
- v0 scope (Step 1): `replay` (`.qdtrec`) and `websocket` sources, the latter fed by `python -m qdt_lab.stream` (synthetic or replay); 1D trace, 2D heatmap, live update. Simulated-device streams arrive at Step 2, `registry` at Step 3, real instruments at Step 5 — all through the same `websocket` source. Nothing else until each step's exit criteria pass.
