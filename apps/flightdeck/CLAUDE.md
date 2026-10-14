# apps/flightdeck — package rules

Flight Deck is the front end. Restarted from scratch (ADR 0005). TypeScript. Transport and renderer class are decided (ADR 0008): WebSocket + Arrow IPC, WebGL 2D. The 2D renderer is raw WebGL2 with no library (ADR 0013, closing #9); `pnpm bench` reproduces Analysis 0002; in CI `--assert --latency-advisory` gates the rendered rate and reports latency (the latency target is evidenced by `bench/results/`). Browser pixel tests: `pnpm build && pnpm test:e2e`.

## Entry gate (ADR 0011)
UI code may be written once `docs/FINISH_LINE.md` is authored (done) and the `Dataset` stream contract is **drafted** in `qdt-schemas` with ADRs (done: ADR 0009, 0010). The contract *freeze* (after Probe 01) gates Step 1's exit, not UI work. Until the freeze:
- consume only the generated types and the wire protocol of ADR 0010; never hand-code around a draft field;
- a contract change regenerates `src/schema/` and must keep every Flight Deck test green in the same commit.

## Rules
- Rule 8: never import an instrument driver; never branch on which instrument produced a `Dataset`. `scripts/check_imports.py` greps for violations. The only permitted read of `dataset.source` is `registry_ref`, to label the view (ADR 0027); `test/render.test.ts` enforces it.
- All data enters through a `Source` implementation (`replay`, `websocket`, later `registry`). A new source must pass the source-equivalence test: the same `Dataset` through any source renders identically.
- Types under `src/schema/` are **generated**: `data.ts` from `packages/qdt-schemas/exports/jsonschema/data.schema.json` (`pnpm gen:types`) and `api.ts` from `packages/qdt-server/exports/openapi.json` (`pnpm gen:api`, ADR 0034); CI fails on drift. Never edit them by hand.
- The control path (Step 4b, ADR 0032): `src/api/client.ts` is the only code that talks to qdt-server, over HTTP, with the generated `api.ts` types; `src/control/` builds schema objects from forms (`sweeps.ts`, `methods.ts`, `sequence.ts` — the pulse-sequence editor model, a form over `PulseSequence` whose columns are type-checked against the generated types, ADR 0035: pure, unit-tested) and wires the panel (`panel.ts`). What is drawn stays a function of the Dataset stream; the panel only asks the server to put things on it.
- Every announced Dataset is kept and selectable (`#datasets`); the newest is shown as it arrives. `e2e/control.test.ts` is the Step 4b exit: it spawns `python -m qdt_server` and drives the panel.
- Transforms (derivative, filter, normalize) are client-side on typed arrays; no server round-trip per toggle. The variable picker and "minus" (a − b of two same-shape variables, ADR 0037) are view options too.
- Scope: `replay` (`.qdtrec`) and `websocket` sources (fed by `python -m qdt_lab.stream`, `python -m qdt_registry serve`, or `qdt-server`); 1D trace, 2D heatmap, live update, overlays; from Step 4b the control panel. Real instruments (Step 5) arrive through the same `websocket` source and the same API; nothing in `src/` changes for them.
