# 0015 — Dataset stream contract frozen against Probe 01; time alignment is the producer's job

**Status:** Accepted
**Date:** 2026-10-12
**Step:** 1

## Context
ADR 0009 drafted the `Dataset` contract (`data.py`: envelope-only chunks, index-range regions, implicit or
streamed coordinates) and ADR 0010 the wire protocol, both explicitly provisional until Probe 01 measured how
the OPX actually delivers results. The OPX half of Probe 01 ran on 2026-10-11 (OPX1000, QOP 3.7.1, qm-qua
1.4.1; `docs/probes/01-stream-semantics.md`, raw data in `bench/fixtures/probe01/`). The scope half has not
run. What the OPX half established:

- **Addressing is positional.** Fetched values equal the flat loop index on every complete fetch; nothing
  travels in band. Coordinates follow from the sweep definition.
- **Granularity is whatever stream processing declares.** `save_all` per point yields any number of points
  per poll, so partial lines occur; `buffer(M).save_all` yields only whole lines; `buffer(N,M).save` yields
  **nothing until the frame completes** (`count_so_far` stays 0, `fetch_all` returns `None`, and near
  completion the client raises on a non-integral fill).
- **Rate.** 10⁶ points/s sustained for 5 s with no loss, per line and per point; unpaced bursts ≈ 3×10⁶
  points/s. The OPX → client path is not the bottleneck at the Analysis 0001 ceiling.
- **Poller cost.** Each `fetch` costs a fixed ≈ 17 ms; new data becomes visible only at the ≈ 30 ms poll
  loop; at 10⁶ points/s a single poller spends ≈ 65 % of wall time fetching.
- **Runtime parameters.** Step count, step size and averaging change on one compiled program through an
  int input stream; fixed-typed input streams do not compile on QOP 3.7.1.
- **Dtype.** Int saves fetch as int64; a timestamp stream gives int64 in 4 ns clock cycles at negligible cost.

For the scope, the HD3-Series Programmer's Guide establishes that a record's time axis is
`xorigin + i·xincrement` and that `xorigin` can differ per capture (`:WAVeform:SEGmented:XLISt? RELXorigin`).
ADR 0009 noted that a streamed coordinate is 1-D per dimension, so a per-record axis cannot be expressed; it
left to the freeze whether that is needed. The human agreed on 2026-10-11 to the direction recorded below.

## Decision
Freeze the Step 1 schema slice (`data.py`: `Dataset`, `Dimension`, `LinearCoordinate`, `IndexedCoordinate`,
`StreamedCoordinate`, `DataVariable`, `SourceDescriptor`, `IndexSlice`, `DatasetChunk`, `Annotation`,
`DatasetMessage`, `AnnotationMessage`, `CHUNK_METADATA_KEY`) and the ADR 0010 wire protocol exactly as they
stand, with no change from the draft. A `Dataset`'s declared coordinates are exact and meeting them is the
producer's responsibility: time alignment stays out of the schema.

## Consequences
- Easier: every Probe 01 delivery shape (point, partial line, whole line, several rows, whole frame) is a
  hyperrectangle, so `DatasetChunk.region` already covers the OPX path with implicit coordinates and no
  in-band metadata; `Dataset.payload_shapes` is the single validator for all of them. Flight Deck, the
  stream server, the recordings and the generated TS types need no change; the `.qdtrec` fixtures stay valid.
- Harder: a per-record time axis is not expressible, by decision. A scope driver (Step 5) either makes
  alignment deterministic in hardware (shared 10 MHz reference, trigger on that clock) or shifts or resamples
  each record onto the declared `LinearCoordinate` using the preamble `xorigin`, records what it did in
  `Dataset.attrs`, and may publish the residual as an ordinary `DataVariable` over the record dimension (its
  own chunks, since chunk variables must span the region). Raw records with preambles go to raw storage
  (Step 3). The conformance suite asserts records land on the declared grid.
- Harder: the latency budget is tight at the ceiling. Analysis 0001 §4 left ≈ 30 ms for the producer's
  cadence; the measured OPX floor is the ≈ 30 ms poll loop (≈ 17 ms fixed per `fetch`). The ≤ 50 ms
  glass-to-glass target therefore holds only when the OPX source polls continuously on a dedicated thread,
  with no sleep between fetches and one poller per program.
- Must now: any change to `data.py` or the wire protocol bumps `schema_version`, adds a migration and a
  fixture at the old version, and carries an ADR (`packages/qdt-schemas/CLAUDE.md`). Live OPX sources never
  use whole-frame buffering (invisible until complete); the default is per-line delivery, with per-point
  delivery when a line takes longer than the live-update target so partial lines stay visible. A poll
  result that is not a hyperrectangle (a line tail plus following rows) is split into several chunks, as
  the reference `SyntheticMap` already does. Timestamps, when published, go as an ordinary int64 or float64
  `DataVariable` in a physical unit; clock cycles are a driver detail. `SweepDefinition.backend_payload`
  (Step 2) must express runtime-variable parameters as ints, with fractional values as scaled ints and the
  scale recorded. Analysis 0001 §5's "≈ 10× margin" is about processed-result physics, not transport; the
  synthetic source's 10⁶ points/s default sits at the measured sustained ceiling, ≈ 3× under the burst
  ceiling, and remains the design target.
- Step 1 exits with the scope half of Probe 01 deferred: it becomes Step 5 driver input (offset magnitude,
  whether resampling is worth it; `scope_findings.json` and the Scope column when the HD304MSO is available).

## Alternatives considered
- Per-record streamed coordinate (a 2-D `StreamedCoordinate` over record × time) — rejected: it moves a
  driver's alignment problem into every consumer (Flight Deck would have to resample before drawing a map),
  contradicts the definition-is-the-truth property the OPX path has, and the residual can already be
  published as data.
- Per-chunk coordinate offset field on `DatasetChunk` — rejected: same consumer burden in a smaller box, and
  it makes `region` ambiguous (index space vs shifted coordinate space).
- Wait for the scope run before freezing — rejected: the Programmer's Guide already answers the structural
  question (origins differ per capture); the run only measures the magnitude, which changes the driver,
  not the schema.
- Fix the chunk granularity in the contract (always whole lines) — rejected: partial lines are the only way
  a slow sweep (10³ points/s over a 2048-wide line is 2 s per line) looks live; the region model carries
  both at no cost.
