# Step 1 — Dataset contract + Flight Deck v0

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Draft the `Dataset` stream contract against the finish-line sketch and the Analysis 0001 design targets, stand up Flight Deck v0 consuming it from synthetic and replay sources, and freeze the contract once Probe 01 confirms chunk semantics.

## Schema slice
`data.py`: `Dataset`, `DatasetChunk`, `Annotation`, `SourceDescriptor`. Frozen at exit (ADR required).

## Deliverables
- Contract derived from `docs/FINISH_LINE.md`; Arrow-encoded chunks + JSON/protobuf envelope (ADR 0005)
- **Probe 01** (`docs/probes/01-stream-semantics.md`, scripts in `bench/probes/probe01/`): one-off, no device, no files — records delivery granularity, addressing, cadence, and QUA runtime constraints. Gates the contract *freeze*, not the draft. Needs lab access; the draft and synthetic source do not wait for it.
- `qdt-lab/stream/`: stream server; `synthetic` and `replay` sources
- `apps/flightdeck`: WebSocket + Arrow IPC transport and WebGL 2D renderer per ADR 0008; WebGL library chosen by benchmark as tie-breaker; `Source` abstraction; 1D trace, 2D heatmap, live update; generated TS types with drift check

## L0 tests (CI)
- replay source with committed synthetic datasets; snapshot tests on rendered output
- source-equivalence: same `Dataset` via synthetic, replay, live-mock renders identically
- throughput test at the Analysis 0001 targets (2048² float32, 10⁶ pts/s, ≤ 50 ms)
- import-boundary test for rule 8

## L1 tests (bench loopback)
- Probe 01 run once; Findings table filled; raw timing CSVs under `bench/fixtures/probe01/`

## L2 tests (surrogate DUT)
- none

## Exit criteria
- contract frozen with ADR; TS types generated in CI
- Flight Deck renders a 2048² map live from the synthetic source within the Analysis 0001 latency target
- contract-freeze ADR cites Probe 01 findings; #9 WebGL library choice recorded

## Open decisions
- #8 — CLOSED by ADR 0008 (WebSocket + Arrow IPC)
- #9 — CLOSED by ADR 0013 (raw WebGL2, no library; Analysis 0002)
- Probe 01 findings (chunk semantics) — CLOSED by ADR 0015 on the OPX half; scope half deferred to Step 5 entry
- Flight Deck UI starts against the drafted contract (ADR 0011); the freeze gates exit, not UI work

## Status
DONE (2026-10-12; contract frozen by ADR 0015; Probe 01 scope half deferred to Step 5)
