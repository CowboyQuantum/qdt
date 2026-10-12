# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 2 — Experiments over a simulated device → `docs/steps/02-experiments-over-simulated-device.md`
**Branch:** `claude/session-plan-review-wudauu` (session-assigned name; restarted from `main` after PR #4.
Every session ends with a PR against `main`; the human merges)
**Last session:** 2026-10-12 — session (11): `qdt-sim` written fresh (ADR 0020): `DoubleDotModel`, noise
models, `SimulatedDevice` behind all three protocols, scenarios + committed fixture, `python -m qdt_sim`
streams a stability diagram live. The first Step 2 exit criterion is met end to end.

## Step 2 exit criteria
| Criterion | State |
|---|---|
| `SweepDefinition` round-trips and runs on `SimulatedDevice`, live in Flight Deck | ✔ `python -m qdt_sim` → `StreamServer` → Flight Deck `?ws=`; collected over WebSocket in the session (32² and 96² maps). Human to eyeball in the browser |
| stand + activity + pulse slices frozen with ADR | ✘ objects complete; freeze ADR at exit |
| Protocols frozen with ADR (second deliberate freeze, ADR 0007) | ✘ complete (ADR 0016/0017); freeze ADR at exit |
| L0: dry-run count/order/shape; reproducibility; scenario within tolerance; conformance on all `Simulated*` | ✔ 167 tests |

## Done
- Steps 0–1 DONE. ADR 0001–0020. Contract frozen (ADR 0015). CI green on `main` at 696ad20.
- **`qdt-sim`** (`dot.py`, `noise.py`, `device.py`, `scenarios.py`, `__main__.py`; package CLAUDE.md):
  constant-interaction double dot (capacitance matrices, Boltzmann occupation, periodic Coulomb-peak
  sensor); `WhiteNoise`, `TelegraphNoise` (exact propagator), `OneOverFNoise` (fluctuator ensemble),
  `Composite`; `SimulatedDevice` = `LevelSource` + `LevelSense` + `Sequencer` on roled vendor channels,
  pulses add to DC (bias tee), device clock drives noise, shots sample the charge state; `compile` accepts
  only backend `simulated` and interprets the `SimulatedEmitter` body. Oracle test: no-noise sweep equals
  `model.current` on the grid. Fixture `tests/fixtures/stability_24x32.npy` (seed 7, 3 shots mean)
  reproduced at rtol 1e-9; regenerate with `scripts/make_sim_fixtures.py`.
- **Experiments as data** (ADR 0018/0019): `PulseSequence`, `SweepDefinition`, `ExecutionPlan`,
  `compile_sweep`, `Executor`, `SimulatedEmitter`. Tutorials 00–01.
- **Protocols + twins + conformance** (ADR 0016/0017). **Stream + Flight Deck** (ADR 0010–0014).

## In flight
- Nothing uncommitted. PR against `main` open for this session; human merges.

## Known broken / not yet real
- Model has no tunnel coupling, spin, valley or Pauli blockade; pulses are quasi-static (durations only
  advance the clock). Each is an ADR when a sweep needs it. Per-shot Python loop: fine to ~10⁵ pixels.
- Flight Deck shows the first Dataset only, no axes/colorbar/cursors/zoom, and no display reduction over
  `repeat` yet, so `--repeats 0` streams passes it cannot average on screen.
- `test_wire_path_keeps_design_target_line_rate` is wall-clock bound off hardware (passed this run; fails
  ~2/3 on the 4-vCPU container). Decide advisory treatment (cf. ADR 0014).
- QUA emitter (Step 5, `[opx]`). Scope captures per stepped point deferred (ADR 0019). Probe 01 scope
  half unrun. Server history unbounded (Step 6). `FINISH_LINE.md` TODO (human). `BENCH.md` skeleton; DUT #10.

## Next action
**Human:** merge the open PR, check CI; run `uv run python -m qdt_sim` and `pnpm dev` in `apps/flightdeck`
with `?ws=ws://127.0.0.1:8765` and confirm the live honeycomb renders.
**Then** close Step 2: a session on `step-2/freeze` writes the two freeze ADRs (capability protocols; stand +
activity + pulse slices), reviews each protocol signature and schema object against what the executor and
`SimulatedDevice` actually needed, adds the Flight Deck display reduction over `repeat` if small, marks the
step DONE and opens Step 3 (registry).

## Decisions pending (see plan §12)
- #10 surrogate DUT design — by Step 5 entry. #2 `payload_hdf5` location — Step 3.
- Whether the stream line-rate test becomes advisory off hardware (see Known broken).
