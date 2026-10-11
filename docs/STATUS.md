# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `main` (`step-1/dataset-contract` merged locally; not pushed — pushing stays manual)
**Last session:** 2026-10-11 — session (2): contract draft + synthetic sources; ADR 0009.

## Done
- Step 0 complete; CI green on `main`; ADR 0001–0008 merged; `FINISH_LINE.md` authored with design targets.
- Analysis 0001 + ADR 0008: WebSocket + Arrow IPC, WebGL 2D. #8 closed; #9 reduced to WebGL library choice.
- Probe 01 spec and scripts written (`docs/probes/01-stream-semantics.md`, `bench/probes/probe01/`), **not run**.
- **`qdt_schemas/data.py` (DRAFT, not frozen):** `Dataset`, `Dimension`, `Linear/Indexed/StreamedCoordinate`,
  `DataVariable`, `SourceDescriptor` (kind only, rule 8), `DatasetChunk` (envelope: `region` of `IndexSlice`s +
  payload names + `explicit_coords`), `Annotation`. `Dataset.payload_shapes(chunk)` and `check_annotation`.
  Design recorded in ADR 0009.
- **`qdt_lab/stream/`:** `Frame` (envelope + arrays, `check`), `assemble` (frames → `xarray.Dataset`),
  `SyntheticMap` (OPX-shaped, defaults = design targets 2048² float32 @ 10⁶ pts/s, any granularity),
  `SyntheticRecords` (scope-shaped, streamed time axis). Content is a pure function of (seed, index).
- 53 tests + `check_all.sh` green locally.

## In flight
- Nothing uncommitted. `main` is ahead of `origin/main`; human to push.

## Known broken / not yet real
- Probe 01 unrun → contract cannot freeze. Two questions it must answer for ADR 0009's draft: per-record
  scope time axis (streamed coords are 1-D/shared today), and OPX partial-buffer visibility.
- No Arrow encoding yet (no `pyarrow` dependency); no stream server; no replay source; no JSON Schema / TS export.
- Pacing test (`test_map_is_paced_to_points_per_second`) is wall-clock; watch for CI flakiness.
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets.
- Probe scripts' `qm-qua` API names unverified. `docs/BENCH.md` skeleton. Surrogate DUT not built.

## Next action
Step 1 session (3), on a new `step-1/stream-server` branch: add `pyarrow` to `qdt-lab` (check pins per ADR 0006),
Arrow IPC encode/decode for `Frame` (round-trip test), the WebSocket stream server (`Dataset` message, then
`DatasetChunk` envelope + binary frame, `Annotation`s), and the `replay` source over committed synthetic
datasets. Then JSON Schema export of `data.py` for TS type generation.

## Decisions pending (see plan §12)
#9 WebGL library (Step 1 benchmark, tie-breaker). Contract freeze (after Probe 01; revisits ADR 0009). #10 DUT design — by Step 5 entry.
