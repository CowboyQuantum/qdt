# Step 1 — Dataset contract + Flight Deck v0

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Freeze the `Dataset` stream contract against the finish-line sketch and measured instrument reality, and stand up Flight Deck v0 consuming it from synthetic and replay sources.

## Schema slice
`data.py`: `Dataset`, `DatasetChunk`, `Annotation`, `SourceDescriptor`. Frozen at exit (ADR required).

## Deliverables
- Contract derived from `docs/FINISH_LINE.md`; Arrow-encoded chunks + JSON/protobuf envelope (ADR 0005)
- **L1 probe:** a one-off script (not a driver) that acquires from the OPX and the scope and records real stream envelope — chunk shape, rate, available metadata — into `docs/BENCH.md`. The synthetic source emulates this envelope.
- `qdt-lab/stream/`: stream server; `synthetic` and `replay` sources
- `apps/flightdeck`: stack chosen by throughput benchmark (Open Decisions #8, #9); `Source` abstraction; 1D trace, 2D heatmap, live update; generated TS types with drift check

## L0 tests (CI)
- replay source with committed synthetic datasets; snapshot tests on rendered output
- source-equivalence: same `Dataset` via synthetic, replay, live-mock renders identically
- throughput benchmark at the measured OPX-realistic chunk rate
- import-boundary test for rule 8

## L1 tests (bench loopback)
- probe script run once; envelope recorded in `docs/BENCH.md` (no bench/ report required)

## L2 tests (surrogate DUT)
- none

## Exit criteria
- contract frozen with ADR; TS types generated in CI
- Flight Deck renders a 2D map live from the synthetic source at the measured chunk rate
- Open Decisions #8 and #9 resolved by ADR

## Open decisions
- #8 stream transport
- #9 Flight Deck stack
- Open input: largest 2D map to render (shape, dtype). Needs lab access; until measured, the benchmark uses a provisional value marked as such.
- Open input: fastest OPX chunk rate (chunks/s, chunk shape). Needs lab access (L1 probe); same provisional treatment.

## Status
IN PROGRESS
