# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 1 — Dataset contract + Flight Deck v0 → `docs/steps/01-dataset-contract-and-flightdeck.md`
**Branch:** `step-1/probe01-scripts` (on top of the unmerged `step-1/flightdeck-benchmark`; neither merged to `main`; pushing stays manual)
**Last session:** 2026-10-11 — session (5): renderer benchmark, #9 closed (ADR 0013, Analysis 0002), browser pixel test, CI target assertion; then Probe 01 scripts reviewed and rewritten for OPX1000 / HD304MSO.

## Step 1 exit criteria
| Criterion | State |
|---|---|
| Contract frozen with ADR; TS types generated in CI | TS types generated + drift-checked in CI ✔ · freeze ✘ (waits on Probe 01) |
| Flight Deck renders a 2048² map live from the synthetic source within the latency target | ✔ steady-state p95 17 ms (RTX 4090) / 11 ms (SwiftShader) vs ≤ 50 ms; asserted in CI |
| Contract-freeze ADR cites Probe 01 findings; #9 choice recorded | #9 ✔ (ADR 0013) · freeze ADR ✘ (Probe 01) |
| L1: Probe 01 run; Findings filled; CSVs in `bench/fixtures/probe01/` | ✘ needs lab access |

**Everything in Step 1 that does not need the lab is done.** The remaining exit items are Probe 01 and the
freeze ADR that cites it.

## Done
- ADR 0001–0013. Analysis 0001 (stream budget) and 0002 (renderer benchmark).
- **Probe 01 ready to run** (`bench/probes/probe01/LAB_GUIDE.md` is the lab guide). Rewritten 2026-10-11 for the
  lab's OPX1000 (LF-FEM; API v2 with v1 fallbacks; `qm-qua` deprecations handled) and Keysight HD304MSO:
  5 s runs on a 10³–10⁶ pts/s + unpaced ladder per line and per point, fetch cost, data loss; whole-frame
  partial visibility; one compiled program re-run with new step count / step / averaging via input streams,
  IO1 via pause/resume; timestamp-stream cost; scope acquire vs transfer and per-capture time-axis origin.
  `--offline-check` builds every QUA program and validates the config without hardware (passes with
  qm-qua 1.4.1; verified to fail on a bad config). Rate-ladder rationale in the probe doc.
- **Contract draft** `qdt_schemas/data.py` (ADR 0009) + wire wrappers; JSON Schema export with drift check.
- **`qdt_lab/stream/`** (ADR 0010): Arrow IPC wire codec, history-backed `StreamServer` (`feed` publishes the
  Dataset, its annotations, then frames; `wait_for_client`), reference client, `.qdtrec` + `ReplaySource`,
  synthetic sources. CLI: `uv run python -m qdt_lab.stream [--size N --rate PTS/S --replay FILE --speed X
  (0=unpaced) --wait-for-client]` on `ws://127.0.0.1:8765`.
- **Fixtures** `packages/qdt-lab/tests/fixtures/stream/` (`.qdtrec` + `.expected.json` oracles);
  regenerate with `uv run python scripts/make_stream_fixtures.py`.
- **`apps/flightdeck`** (ADR 0011, 0012, 0013) — run pnpm from `apps/flightdeck` (corepack pins 9.15.9):
  - generated types; decoder; `DatasetStore`; replay and WebSocket sources behind one `Decoder`.
  - `render/map.ts`: `MapRenderer` interface — `webgl2` (raw, default) and `cpu` (fallback/reference);
    canvas-2D 1D trace (visually checked on the records fixture 2026-10-11).
  - URL params: `?ws=`, `?replay=<url>&speed=`, `?renderer=webgl2|cpu`, `?bench=1`.
  - `pnpm test` (21 unit), `pnpm test:e2e` (browser pixel test, WebGL vs CPU reference, needs `pnpm build`;
    verified to fail on a flipped image), `pnpm bench [--gpu hardware|swiftshader] [--assert] [--out …]`.
- **CI:** `l0` (Python 78 tests + check_all), extras matrix, `flightdeck` (types drift, typecheck, unit, build,
  e2e, `bench --assert` at 2048² / 10⁶ pts/s on SwiftShader).

## In flight
- Nothing uncommitted. Branch awaits merge; CI has not yet run the new e2e/bench steps.

## Known broken / not yet real
- Probe 01 unrun → no freeze (per-record scope time axis; OPX partial-buffer visibility; point-wise chunk rate).
- First-frame latency spike ~100 ms (GPU) / ~290 ms (SwiftShader): texture allocation + shader compile on
  the first chunk. Steady state is fine; pre-allocating on Dataset announce would remove it.
- Flight Deck has no axes, colorbar, cursors, line cuts or zoom; only the first Dataset is shown.
- `bench --assert` and wall-clock tests may be flaky on slow CI runners (watch the first runs).
- Server history unbounded; server ignores client messages ("up" edge is Step 6).
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets (now measured: Analysis 0002).
- Probe scripts verified offline only; execution-time APIs (result handles, input-stream push, IO, pause/resume) are first exercised in the lab — run `--quick` first. `docs/BENCH.md` skeleton. Surrogate DUT not built.

## Next action
**Human, in the lab:** run Probe 01 per `bench/probes/probe01/LAB_GUIDE.md` (QOP version → matching `qm-qua` →
offline check → `--quick` → full OPX run → scope run → commit `bench/fixtures/probe01/`). Then a session on
`step-1/contract-freeze` reads the findings, fills the probe doc's Findings table, revisits ADR 0009/0010
against them (per-record scope time axis, OPX partial-buffer visibility, point-wise rates), writes the freeze
ADR, and closes Step 1. The human chose to wait for the lab rather than polish Flight Deck or start Step 2.

## Decisions pending (see plan §12)
Contract freeze (after Probe 01; revisits ADR 0009/0010). Whether to start Step 2 before Probe 01 (above).
#10 DUT design — by Step 5 entry.
