# apps/flightdeck — package rules

Flight Deck is the front end. Restarted from scratch (ADR 0005). TypeScript; stack chosen at Step 1 by benchmark (plan Open Decisions #8, #9).

## Entry gate
No UI code until `docs/FINISH_LINE.md` is filled in by a human and the `Dataset` / `DatasetChunk` / `Annotation` contract is frozen in `qdt-schemas` with an ADR.

## Rules
- Rule 8: never import an instrument driver; never branch on which instrument produced a `Dataset`. `scripts/check_imports.py` greps for violations.
- All data enters through a `Source` implementation (`replay`, `live`, later `registry`, `sim`). A new source must pass the source-equivalence test: the same `Dataset` through any source renders identically.
- Types under `src/schema/` are **generated** from the JSON Schema export (`pnpm gen:types`); CI fails on drift. Never edit them by hand.
- Transforms (derivative, filter, normalize) are client-side on typed arrays; no server round-trip per toggle.
- v0 scope (Step 1): synthetic + replay sources, 1D trace, 2D heatmap, live update. `live` source arrives at Step 2, `registry` at Step 3. Nothing else until each step's exit criteria pass.
