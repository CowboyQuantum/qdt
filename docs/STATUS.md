# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `main` (`step-1/probe01-lab` fast-forwarded into it; not pushed — pushing stays manual)
**Last session:** 2026-10-11 — session (6), in the lab: Probe 01 OPX half run on the OPX1000 (QOP 3.7.1,
qm-qua 1.4.1); three script fixes; Findings table filled for the OPX. Scope half not run (no scope access).

## Step 1 exit criteria
| Criterion | State |
|---|---|
| Contract frozen with ADR; TS types generated in CI | TS types generated + drift-checked in CI ✔ · freeze ✘ |
| Flight Deck renders a 2048² map live from the synthetic source within the latency target | ✔ steady-state p95 17 ms on a hardware GPU vs ≤ 50 ms (`apps/flightdeck/bench/results/`, Analysis 0002). CI gates the rendered rate (≥ 95 % of 10⁶ pts/s); latency is printed but advisory there |
| Contract-freeze ADR cites Probe 01 findings; #9 choice recorded | #9 ✔ (ADR 0013) · freeze ADR ✘ |
| L1: Probe 01 run; Findings filled; CSVs in `bench/fixtures/probe01/` | OPX ✔ · scope ✘ (needs the HD304MSO, ~10 min; no longer gates the freeze if the proposed direction below holds) |

## Done
- ADR 0001–0013. Analysis 0001 (stream budget) and 0002 (renderer benchmark).
- **Probe 01, OPX half** — results in `bench/fixtures/probe01/` (dry run in `quick/`), Findings in
  `docs/probes/01-stream-semantics.md`. Headlines for the freeze:
  - No data loss up to 10⁶ pts/s sustained (5 s), per line and per point; unpaced bursts ≈ 3×10⁶ pts/s.
  - Delivery granularity is set by stream processing: per point gives partial lines, per line only whole
    lines, whole frame **nothing until complete** (client API refuses a partially filled buffer).
  - Positional addressing confirmed (values == flat loop index); int64; no in-band coordinates.
  - Each `fetch` costs a fixed ≈ 17 ms; visibility is resolved only to the ≈ 30 ms poll loop; at 10⁶ a single
    poller spends ≈ 65 % of its time fetching.
  - One compiled program: step count, step and averaging change at run time via an **int** input stream; IO1
    works via pause/resume. **Fixed-typed input streams don't compile on QOP 3.7.1** → scaled ints.
  - Timestamp streams are in 4 ns clock cycles; negligible cost.
- Script fixes this session (`fix(bench)` commits): int step input stream + `fixed_input_stream_compiles`
  check; wait for "Running" after API v2 `add_to_queue`; whole-frame poll runs to completion; timestamp unit
  label. `--offline-check` passes with qm-qua 1.4.1.
- **Contract draft** `qdt_schemas/data.py` (ADR 0009) + wire wrappers; JSON Schema export with drift check.
- **`qdt_lab/stream/`** (ADR 0010): Arrow IPC codec, history-backed `StreamServer`, reference client,
  `.qdtrec` + `ReplaySource`, synthetic sources. CLI: `uv run python -m qdt_lab.stream [--size N --rate PTS/S
  --replay FILE --speed X --wait-for-client]` on `ws://127.0.0.1:8765`.
- **Fixtures** `packages/qdt-lab/tests/fixtures/stream/` (regenerate: `uv run python scripts/make_stream_fixtures.py`).
- **`apps/flightdeck`** (ADR 0011–0013): generated types, decoder, `DatasetStore`, replay/WebSocket sources,
  `webgl2` + `cpu` map renderers, 1D trace; URL params `?ws= ?replay=&speed= ?renderer= ?bench=1`;
  `pnpm test` (21 unit), `pnpm test:e2e`, `pnpm bench`. Run pnpm from `apps/flightdeck`.
- **CI:** `l0` (78 Python tests + check_all), extras matrix, `flightdeck` (types drift, typecheck, unit,
  build, e2e, `bench --assert --latency-advisory`).

## In flight
- Nothing uncommitted. `main` is ahead of `origin/main`; human to push.
- CI was red on `main` only in the bench latency gate (never passed since it was added); fixed on `step-1/ci-bench-latency`, unverified on CI until pushed.

## Known broken / not yet real
- Probe 01 scope half unrun → per-capture origin magnitude unmeasured (Step 5 driver input under the proposed direction).
- Unpaced OPX runs are ≈ 0.7 s bursts, not 5 s sustained; the 10⁶ point is the sustained figure.
- First-frame latency spike ~100 ms (GPU) / ~290 ms (SwiftShader) on the first chunk; steady state fine.
- Flight Deck has no axes, colorbar, cursors, line cuts or zoom; only the first Dataset is shown.
- SwiftShader latency is machine noise, not a code signal: steady p95 78 / 334 ms on two CI runs of identical code, 1250 ms on a MacBook, 11 ms on the Analysis 0002 machine. Hence `--latency-advisory` in CI. Rerun the hardware bench when the renderer changes.
- Server history unbounded; server ignores client messages ("up" edge is Step 6).
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets (measured: Analysis 0002).
- `docs/BENCH.md` skeleton. Surrogate DUT not built.

## Next action
**Human:** push `main` and check CI.
**Then** a session on `step-1/contract-freeze` reads the Findings, revisits ADR 0009/0010 against them
(chunks as index ranges into the definition; per-line vs per-point chunking; poller cost at 10⁶; int-only
runtime parameters in `SweepDefinition.backend_payload`), adopts or rejects the time-alignment direction
below, writes the freeze ADR, and closes Step 1. It does not wait for the scope.
**Whenever the HD304MSO is available:** run the scope half (LAB_GUIDE step 5, ~10 min, no OPX) and commit
`scope_findings.json`; a session fills the Scope column. It confirms the SCPI commands and the offset size.

## Decisions pending (see plan §12)
**Scope time axis — proposed direction (human agreed 2026-10-11; to be decided in the freeze ADR):** keep time
alignment out of the schema. Rule: a `Dataset`'s declared coordinates are exact; meeting them is the producer's
job. The scope driver either makes alignment deterministic in hardware (shared 10 MHz reference + trigger on
that clock) or shifts/resamples each record onto the declared `LinearCoordinate` using the preamble's
`xorigin`, records what it did in `Dataset.attrs`, and may publish the residual as an ordinary `DataVariable`
(e.g. `trigger_offset` over the record dim, in its own chunks — chunk variables must span the region,
`data.py` `payload_shapes`). Raw records with preambles go to raw storage (Step 3); the conformance suite
asserts records land on the declared grid. Evidence that origins differ per capture: the HD3-Series
Programmer's Guide (`:WAVeform:XORigin?`; `:WAVeform:SEGmented:XLISt? RELXorigin` returns a per-segment
origin). Consequence: **the freeze no longer waits for the scope run**; the scope half becomes Step 5 driver
input (offset magnitude, whether resampling is worth it). The freeze session should still confirm nothing
else in ADR 0009/0010 depends on a per-record axis.
#10 DUT design — by Step 5 entry.
