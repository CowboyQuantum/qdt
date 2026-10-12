# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 2 — Experiments over a simulated device → `docs/steps/02-experiments-over-simulated-device.md`
**Branch:** `claude/session-plan-review-wudauu` (session-assigned name; the work is the `step-1/contract-freeze`
session STATUS asked for. Human merges to `main`; pushing `main` stays manual)
**Last session:** 2026-10-12 — session (7): Step 1 closed. ADR 0015 freezes the `Dataset` contract and the
wire protocol against the Probe 01 OPX findings, unchanged from the draft; time alignment is the producer's job.

## Step 1 — DONE (2026-10-12)
| Criterion | State |
|---|---|
| Contract frozen with ADR; TS types generated in CI | ✔ ADR 0015; `data.py` marked frozen; TS types drift-checked in CI |
| Flight Deck renders a 2048² map live within the latency target | ✔ p95 17 ms on a hardware GPU (Analysis 0002); CI gates rendered rate, latency advisory (ADR 0014) |
| Freeze ADR cites Probe 01 findings; #9 recorded | ✔ ADR 0015 · ADR 0013 |
| L1: Probe 01 run; Findings filled; CSVs committed | OPX ✔ · scope half deferred to Step 5 entry by ADR 0015 |

## Done
- ADR 0001–0015. Analysis 0001 (stream budget), 0002 (renderer benchmark).
- **Contract frozen** (`qdt_schemas/data.py`, ADR 0009 + 0010 + 0015). Any change: `schema_version` bump,
  migration, old-version fixture, ADR. JSON Schema export drift-checked; TS types generated from it.
- **Probe 01 OPX half**: findings in `docs/probes/01-stream-semantics.md`, data in `bench/fixtures/probe01/`.
  Consequences recorded in ADR 0015 (per-line default, no whole-frame buffering live, ~30 ms poller floor,
  int-only runtime parameters, timestamps as ordinary data variables).
- **`qdt_lab/stream/`** (ADR 0010): Arrow IPC codec, history-backed `StreamServer`, reference client,
  `.qdtrec` + `ReplaySource`, synthetic sources. CLI: `uv run python -m qdt_lab.stream [--size N --rate PTS/S
  --replay FILE --speed X --wait-for-client]` on `ws://127.0.0.1:8765`.
- **`apps/flightdeck`** (ADR 0011–0014): generated types, decoder, `DatasetStore`, replay/WebSocket sources,
  `webgl2` + `cpu` renderers, 1D trace; `pnpm test` / `test:e2e` / `bench` from `apps/flightdeck`.
- **CI:** `l0` (78 Python tests + check_all), extras matrix, `flightdeck` (types drift, typecheck, unit, build,
  e2e, `bench --assert --latency-advisory`). Green on `main` at 9c683d8.
- `stand.py` already holds the Step 2 stand slice (`ChannelMap`, …), unfrozen.

## In flight
- Nothing uncommitted. This branch is ahead of `main` by the Step 1 close; human to merge and push.

## Known broken / not yet real
- Probe 01 scope half unrun → per-capture origin magnitude unmeasured. Step 5 input: run LAB_GUIDE step 5
  (~10 min, no OPX), commit `scope_findings.json`, fill the Scope column.
- Unpaced OPX runs are ≈ 0.7 s bursts, not 5 s sustained; 10⁶ points/s is the sustained figure.
- First-frame latency spike ~100 ms (GPU) / ~290 ms (SwiftShader); steady state fine.
- Flight Deck has no axes, colorbar, cursors, line cuts or zoom; only the first Dataset is shown.
- SwiftShader latency is machine noise (ADR 0014); rerun the hardware bench when the renderer changes.
- Server history unbounded; server ignores client messages ("up" edge is Step 6).
- `FINISH_LINE.md` TODO open: human to confirm/adjust the design targets (measured: Analysis 0002).
- `docs/BENCH.md` skeleton. Surrogate DUT not built (#10, by Step 5 entry).

## Next action
**Human:** merge this branch to `main`, push, check CI.
**Then** the first Step 2 session on `step-2/protocols` reads `docs/steps/02-experiments-over-simulated-device.md`
and starts with the capability protocols in `qdt-lab/protocols/` (`DCSource`, `Digitizer`, `PulseSequencer`,
`SourceMeasure`), each with a `Simulated*` twin and the single conformance suite, before `activity.py`
(`SweepDefinition`, `ExecutionPlan`). `SweepDefinition.backend_payload` for QUA: int input stream, scaled ints
for fractional values (ADR 0015).

## Decisions pending (see plan §12)
- #10 surrogate DUT design — by Step 5 entry.
- #2 `payload_hdf5` location — Step 3.
