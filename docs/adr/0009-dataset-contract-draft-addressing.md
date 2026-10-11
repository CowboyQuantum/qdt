# 0009 — Dataset contract draft: envelope-only chunks, region addressing, implicit/explicit coordinates

**Status:** Accepted (draft shape; the freeze is a separate ADR after Probe 01)
**Date:** 2026-10-11
**Step:** 1

## Context
ADR 0008 fixed the wire form: JSON envelope plus Arrow IPC binary payload. Analysis 0001 §6 showed the
open questions are about how data is laid out, not how big it is. The OPX delivers positional results
whose coordinates follow from the sweep definition. The scope delivers whole records with an explicit time
axis. Granularity (per point, per line, per frame) is unknown until Probe 01. `qdt-schemas` must stay
numpy-free (package rules). Rule 8 forbids the consumer from learning the producing instrument.

## Decision
`DatasetChunk` is the envelope only: it names an index hyperrectangle (`region`) plus the payload array
names, and arrays never appear in schema objects. Coordinates are either implicit (`linear`, `indexed`,
derived from the `Dataset` definition) or explicit (`streamed`, carried 1-D in the payload of every chunk
whose region covers their dimension). `SourceDescriptor` carries a source *kind*, never an instrument.

## Consequences
- Easier: one addressing model covers point, partial-line, line and multi-row chunks (OPX-shaped) and
  whole records with in-band axes (scope-shaped); `Dataset.payload_shapes(chunk)` lets any producer or
  consumer validate a payload without numpy; unbounded dimensions (`size=None`) allow free-running records.
- Harder: a chunk must be a hyperrectangle, so a ragged or non-rectangular delivery has to be split
  into several chunks.
  A streamed coordinate is 1-D and shared across the other dimensions, so a per-record time axis
  (e.g. trigger jitter) cannot be expressed yet.
- Must now: Probe 01 must answer whether real scope captures need a per-record axis and whether OPX partial
  buffers are visible mid-acquisition. The freeze ADR revisits this draft against those findings. The
  stream server encodes `Frame.arrays` as Arrow IPC.

## Alternatives considered
- Arrays inside the pydantic chunk (base64 or lists) — rejected: pulls numpy into `qdt-schemas` and
  contradicts the binary-payload arithmetic of ADR 0008.
- Separate chunk types for implicit and explicit addressing — rejected: mixed cases (indexed record count ×
  streamed time axis) need both in one chunk.
- Coordinates always explicit — rejected: costs bandwidth on every chunk and drops the definition-is-the-truth
  property the OPX path naturally has.
- Instrument id in `SourceDescriptor` — rejected by rule 8.
