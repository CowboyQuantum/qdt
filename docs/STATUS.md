# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `main` (sessions 3–4 pushed; CI fix `step-1/ci-fix` merged locally, not pushed — pushing stays manual)
**Last session:** 2026-10-11 — session (4): Flight Deck v0 scaffold, decoder, sources, WebGL heatmap, CI job; ADR 0012.

## Done
- Step 0 complete. ADR 0001–0012. Analysis 0001 + ADR 0008: WebSocket + Arrow IPC, WebGL 2D. ADR 0011: UI work
  proceeds against the drafted contract; the freeze gates Step 1 exit only.
- Probe 01 spec and scripts written (`docs/probes/01-stream-semantics.md`, `bench/probes/probe01/`), **not run**.
- **Contract draft** `qdt_schemas/data.py` (ADR 0009) + wire wrappers; JSON Schema export
  `packages/qdt-schemas/exports/jsonschema/data.schema.json` with drift check in `check_all.sh`.
- **`qdt_lab/stream/`** (ADR 0010): Arrow IPC wire codec, history-backed `StreamServer` (`feed` publishes the
  Dataset, its annotations, then frames), reference client, `.qdtrec` recordings + `ReplaySource`,
  `SyntheticMap`/`SyntheticRecords`, `assemble`. CLI: `uv run python -m qdt_lab.stream [--size N --rate PTS/S
  --replay FILE --speed X(0=unpaced)]` on `ws://127.0.0.1:8765`.
- **Fixtures** `packages/qdt-lab/tests/fixtures/stream/`: two `.qdtrec` + `.expected.json` content oracles
  (sha256 per assembled array). Regenerate both: `uv run python scripts/make_stream_fixtures.py`.
- **`apps/flightdeck`** (ADR 0012): pnpm 9.15.9 via corepack (`packageManager`), Vite, TS, Vitest.
  - `pnpm gen:types` / `check:types`: `src/schema/data.ts` generated from the JSON Schema export.
  - `src/stream/`: decoder (Arrow + JSON, `payloadShapes` port), `.qdtrec` parser, `DatasetStore`.
  - `src/sources/`: one `Decoder` behind `ReplaySource` and `WebSocketSource`; `consume()`.
  - `src/render/`: raw WebGL2 heatmap (R32F, `texSubImage2D` per dirty row, viridis in GLSL), CPU reference
    renderer, canvas-2D trace. `src/view.ts`: view by shape only; annotation overlay in data coordinates.
  - `src/main.ts`: `pnpm -C apps/flightdeck dev`, opens `?ws=` (default `ws://127.0.0.1:8765`) or a `.qdtrec` file.
  - Verified visually 2026-10-11: headless Chrome (`--use-angle=swiftshader`) rendered a 512² synthetic map
    streamed from the Python server through the WebGL path.
- **CI:** new `flightdeck` job (uv sync for the e2e test, Node 24, corepack, check:types, typecheck, test, build).
- **Tests:** Python 77; Flight Deck 21 — decoder == Python oracle bit-for-bit, source equivalence across replay /
  WebSocket / real Python server, CPU render snapshot, rule-8 grep. `check_all.sh` green.

## In flight
- Nothing uncommitted. First CI run of sessions 3–4 (run 38178034894) failed; fixed locally, awaiting push:
  - `flightdeck` job: corepack ran from the repo root and fetched the latest pnpm (12) instead of the pinned
    9.15.9 → job now runs with `working-directory: apps/flightdeck`. Run pnpm from that directory locally too.
  - `l0`: recording-vs-regenerated synthetic comparisons failed on Linux for float64 records (fixtures recorded
    on Windows; libm `exp`/`cos` last-ulp differences) → those comparisons now use `rtol=1e-12`; same-bytes
    transport comparisons stay exact. The cross-language oracles hash recorded data, so they are unaffected.

## Known broken / not yet real
- Probe 01 unrun → contract cannot freeze (per-record scope time axis; OPX partial-buffer visibility).
- GPU output is not tested in CI (CPU path only); no throughput/latency test in a real browser yet.
- No axes, colorbar, cursors, line cuts, zoom; 1D trace untested visually; only the first Dataset is shown.
- Server history unbounded; server ignores client messages ("up" edge is Step 6).
- Wall-clock tests (Python pacing/rate, TS paced replay) may be flaky on slow CI runners.
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets.
- Probe scripts' `qm-qua` API names unverified. `docs/BENCH.md` skeleton. Surrogate DUT not built.

## Next action
Step 1 session (5), on `step-1/flightdeck-benchmark`: the browser benchmark that closes #9 and the live exit
criterion — Playwright (or headless Chrome via CDP) driving Flight Deck against `python -m qdt_lab.stream` at the
design targets (2048², 10⁶ pts/s), measuring render latency (chunk `produced_at` → frame drawn) and sustained
rate; raw WebGL2 baseline vs one or two library candidates; record the choice by ADR; add a browser pixel
snapshot of the WebGL path. Then axes/colorbar and the 1D trace check.

## Decisions pending (see plan §12)
#9 WebGL library (benchmark next session; raw WebGL2 is the baseline). Contract freeze (after Probe 01;
revisits ADR 0009/0010). #10 DUT design — by Step 5 entry.
