# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `step-1/stream-server` (not yet merged to `main`; pushing stays manual)
**Last session:** 2026-10-11 — session (3): Arrow wire codec, WebSocket stream server, replay, JSON Schema export; ADR 0010.

## Done
- Step 0 complete. ADR 0001–0010 written. Analysis 0001 + ADR 0008: WebSocket + Arrow IPC, WebGL 2D.
- Probe 01 spec and scripts written (`docs/probes/01-stream-semantics.md`, `bench/probes/probe01/`), **not run**.
- **`qdt_schemas/data.py` (DRAFT, not frozen; ADR 0009):** `Dataset`, `DatasetChunk` (envelope: index `region`
  + payload names + `explicit_coords`), `Annotation`, `SourceDescriptor` (kind only, rule 8), coordinate kinds
  `linear`/`indexed`/`streamed`; wire wrappers `DatasetMessage`/`AnnotationMessage` (`StreamTextMessage`).
- **`qdt_lab/stream/` (ADR 0010):**
  - `wire`: chunk = one Arrow IPC message, one-row batch of `list<dtype>` columns, envelope JSON in schema
    metadata `qdt.chunk`; text messages are `StreamTextMessage` JSON.
  - `StreamServer`: history-backed (late join gets everything), per-client pacing, datasets multiplexed;
    `feed(source)` runs blocking sources in a worker thread. Compression off.
  - `client.subscribe/collect`: reference Python consumer ("live-mock").
  - `ReplaySource` over `.qdtrec` recordings (exact wire bytes); fixtures in `packages/qdt-lab/tests/fixtures/stream/`
    (regenerate: `uv run python scripts/make_stream_fixtures.py`).
  - `SyntheticMap` / `SyntheticRecords`, `assemble`, `Frame`, `Source` protocol.
  - CLI: `uv run python -m qdt_lab.stream [--size N --rate PTS_PER_S --replay FILE]` serves on `ws://127.0.0.1:8765`.
- **JSON Schema export:** `packages/qdt-schemas/exports/jsonschema/data.schema.json` (serialization mode,
  defaulted fields required); `scripts/export_schemas.py --check` runs in `check_all.sh`.
- L0: 74 tests + `check_all.sh` green locally. Includes source equivalence (synthetic == replay == live) and
  ≥ 10⁶ pts/s end-to-end over localhost WebSocket (Python client).

## In flight
- Nothing uncommitted. `step-1/stream-server` awaits merge.

## Known broken / not yet real
- **Flight Deck entry gate conflict (human decision needed):** `apps/flightdeck/CLAUDE.md` says no UI code until
  the contract is *frozen*, but the freeze waits on Probe 01 (lab), and Step 1 / ADR 0008 build Flight Deck v0
  against the *draft*. That file also still says "stack chosen at Step 1 … Open Decisions #8, #9" (8 is closed)
  and its README says "Scaffolded at Step 2". Needs a human edit (or an ADR) before any UI session.
- Probe 01 unrun → contract cannot freeze. Open questions for the freeze: per-record scope time axis (streamed
  coords are 1-D/shared), OPX partial-buffer visibility.
- Server history is unbounded (fine for maps; grows forever for free-running `record` streams). No eviction.
- Server ignores client messages (the "up" edge is Step 6).
- Wall-clock tests (pacing, paced replay, end-to-end rate) may be flaky on slow CI runners.
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets.
- Probe scripts' `qm-qua` API names unverified. `docs/BENCH.md` skeleton. Surrogate DUT not built.

## Next action
Human: resolve the Flight Deck entry-gate conflict above; merge `step-1/stream-server`. Then Step 1 session (4),
on `step-1/flightdeck-v0`: scaffold `apps/flightdeck` (pnpm, TS), `pnpm gen:types` from
`packages/qdt-schemas/exports/jsonschema/data.schema.json` with a CI drift check, a TS stream decoder
(`StreamTextMessage` JSON + Arrow IPC chunk via `apache-arrow`), the `Source` abstraction with `replay` (reading
`.qdtrec`) and WebSocket sources, then the WebGL 2D heatmap. Add the frontend job to CI.

## Decisions pending (see plan §12)
#9 WebGL library (Step 1 benchmark, tie-breaker). Contract freeze (after Probe 01; revisits ADR 0009/0010). #10 DUT design — by Step 5 entry.
