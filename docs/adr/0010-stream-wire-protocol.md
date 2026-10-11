# 0010 — Stream wire protocol, recordings, and server delivery model

**Status:** Accepted (draft protocol; frozen together with the contract after Probe 01)
**Date:** 2026-10-11
**Step:** 1

## Context
ADR 0008 chose WebSocket + Arrow IPC with a JSON envelope. ADR 0009 made `DatasetChunk` envelope-only.
Still open: how an envelope is paired with its arrays on the wire; how arrays of different lengths (a 2D
variable and a 1-D streamed coordinate) share one Arrow message; what replay files are; how late or slow
viewers are served; and how TypeScript types are produced (ADR 0005/0006).

## Decision
Text WebSocket messages carry `DatasetMessage` / `AnnotationMessage` JSON (the `type`-discriminated
`StreamTextMessage`). Each chunk is one binary message: an Arrow IPC stream with a single one-row record
batch, one `list<dtype>` column per payload array (flattened row-major), and the `DatasetChunk` JSON in the
schema metadata under `qdt.chunk`. Replay recordings (`.qdtrec`) store that exact message sequence. The
server keeps the full message history and serves each client from it at that client's own pace.

## Consequences
- Easier: a chunk is self-contained (no envelope/payload pairing state, no ordering hazard between two
  messages); one-row list columns let differently shaped arrays share a batch, and each array still
  decodes zero-copy into a typed array in the browser; replay is byte-faithful to live, so the
  source-equivalence test covers the decoder too; a late client gets the whole Dataset; a slow client lags
  without slowing the producer or other clients; many Datasets multiplex on one connection by `dataset_id`.
- Harder: history is unbounded in memory (a 2048² float32 map ≈ 17 MB per Dataset, fine; a free-running
  `record` stream grows forever). Eviction is not designed yet. Arrow metadata is less convenient to inspect
  than a JSON frame (ADR 0008's `--debug-json` sidecar remains the escape hatch).
- Must now: keep permessage-deflate off on both ends (float payloads barely compress, deflate costs ms/MB);
  clients must lift the default 1 MiB receive limit; regenerate `packages/qdt-schemas/exports/jsonschema/
  data.schema.json` after any `data.py` change (`check_all.sh` fails on drift); regenerate the committed
  `.qdtrec` fixtures (`scripts/make_stream_fixtures.py`) after any wire change.
- Schema export uses serialization mode with `json_schema_serialization_defaults_required` on `QdtModel`, so
  generated TS types treat always-emitted defaulted fields as present.
- `pyarrow` and `websockets` are core `qdt-lab` dependencies (floating, no upper bound, per ADR 0006).

## Alternatives considered
- Envelope as a JSON text message followed by a binary message — rejected: pairing state on both ends, and
  interleaving from multiple producers can mis-pair them.
- Length-prefixed custom frame `[len][JSON][Arrow]` — rejected: a bespoke parser in two languages; Arrow
  metadata already does this.
- One Arrow column per array without lists (record batch of N rows) — rejected: columns in a batch must have
  equal length, so a 2D variable and a 1-D coordinate cannot share one.
- Broadcast-only live delivery (no history) — rejected: late viewers would need a separate snapshot path,
  and the replay/registry sources would diverge from live.
- HDF5 or Arrow files as the replay format — rejected for now: the at-rest form is `qdt-hdf5-v1` in Step 3.
  Replay's job is to reproduce the wire exactly.
