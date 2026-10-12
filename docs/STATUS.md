# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `step-1/probe01-lab` (Probe 01 OPX lab run; not merged, not pushed — merging and pushing stay manual)
**Last session:** 2026-10-11 — session (6), in the lab: Probe 01 OPX half run on the OPX1000 (QOP 3.7.1,
qm-qua 1.4.1); three script fixes; Findings table filled for the OPX. Scope half not run (no scope access).

## Step 1 exit criteria
| Criterion | State |
|---|---|
| Contract frozen with ADR; TS types generated in CI | TS types generated + drift-checked in CI ✔ · freeze ✘ |
| Flight Deck renders a 2048² map live from the synthetic source within the latency target | ✔ steady-state p95 17 ms (RTX 4090) / 11 ms (SwiftShader) vs ≤ 50 ms; asserted in CI |
| Contract-freeze ADR cites Probe 01 findings; #9 choice recorded | #9 ✔ (ADR 0013) · freeze ADR ✘ |
| L1: Probe 01 run; Findings filled; CSVs in `bench/fixtures/probe01/` | OPX ✔ · scope ✘ (needs the HD304MSO, ~10 min, no OPX needed) |

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
  build, e2e, `bench --assert`).

## In flight
- Nothing uncommitted. `step-1/probe01-lab` is ahead of `main`; human to merge and push.
- CI on `main` for c7287b4 (first run of the e2e/bench steps) was still running at session start — check it.

## Known broken / not yet real
- Probe 01 scope half unrun → per-record scope time axis (question 4) unanswered.
- Unpaced OPX runs are ≈ 0.7 s bursts, not 5 s sustained; the 10⁶ point is the sustained figure.
- First-frame latency spike ~100 ms (GPU) / ~290 ms (SwiftShader) on the first chunk; steady state fine.
- Flight Deck has no axes, colorbar, cursors, line cuts or zoom; only the first Dataset is shown.
- `bench --assert` and wall-clock tests may be flaky on slow CI runners.
- Server history unbounded; server ignores client messages ("up" edge is Step 6).
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets (measured: Analysis 0002).
- `docs/BENCH.md` skeleton. Surrogate DUT not built.

## Next action
**Human:** merge `step-1/probe01-lab` into `main` and push. When the HD304MSO is available, run the scope half
(LAB_GUIDE step 5, ~10 min, no OPX needed) and commit its `scope_findings.json`; a Claude session can fill the
Scope column from it.
**Then** a session on `step-1/contract-freeze` reads the Findings, revisits ADR 0009/0010 against them
(chunks as index ranges into the definition; per-line vs per-point chunking; poller cost at 10⁶; int-only
runtime parameters in `SweepDefinition.backend_payload`; per-record scope time axis), writes the freeze ADR,
and closes Step 1.

## Decisions pending (see plan §12)
**Freeze before the scope half?** The OPX answers 3 of the 4 freeze questions. The human decides whether the
freeze session waits for the scope run or freezes now with an explicit per-record time axis as a hedge.
#10 DUT design — by Step 5 entry.
