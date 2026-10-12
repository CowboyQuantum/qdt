# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 2 — Experiments over a simulated device → `docs/steps/02-experiments-over-simulated-device.md`
**Branch:** `claude/session-plan-review-wudauu` (session-assigned name; restarted from `main` after PR #3.
Every session ends with a PR against `main`; the human merges)
**Last session:** 2026-10-12 — session (10): experiments as data. `PulseSequence` (ADR 0018, amends plan
§10), `SweepDefinition` + `ExecutionPlan` (ADR 0019), `qdt_lab/experiment/` compiler, executor, `Emitter`
protocol + `SimulatedEmitter`. Tutorial 01 runs a stability diagram end to end on simulated backends.

## Step 2 exit criteria
| Criterion | State |
|---|---|
| `SweepDefinition` round-trips and runs on `SimulatedDevice`, live in Flight Deck | ◐ round-trips and runs on the generic `SimulatedSequencer` (flat index); `qdt-sim` `SimulatedDevice` ✘; Flight Deck `live` source ✘ |
| stand + activity (+ pulse) slices frozen with ADR | ✘ all objects exist (`stand.py`, `activity.py`, `pulse.py`); freeze ADR at exit |
| Protocols frozen with ADR (second deliberate freeze, ADR 0007) | ✘ all five defined (ADR 0016/0017); freeze ADR at exit |

## Done
- Steps 0–1 DONE. ADR 0001–0019. Contract frozen (ADR 0015). CI green on `main` at b8a2d59.
- **Schema (Step 2 slice, unfrozen):** `stand.py` `InstrumentConfig` (backend, capabilities), `ChannelMap`
  (quantity, settle_s, integration_s), `StandConfig`. `pulse.py` `PulseSequence` (`step`, `ramp`, `wait`,
  `drive`, `measure`, `call`; `Symbol`s; `Segment`s; integer ns). `activity.py` `SequencerProgram`,
  `SweepAxis`, `SensedLevel`, `SymbolBinding`, `ParameterBinding`, `SequencerStage`, `SweepDefinition`
  (axes outer→inner, sensed, stage on the innermost axes, shots, per-result reduce, repeats int|None),
  `ResolvedChannel`, `ExecutionPlan` (structural).
- **`qdt_lab/experiment/`:** `compile_sweep(definition, stand, emitters)`; `Executor(plan, backends).run()
  -> Source` (repeats → stepped row-major with settle → stage per point, frames re-keyed; sensed per line;
  final on last); `Emitter` protocol; `SimulatedEmitter` (body = sequence JSON + symbol→parameter map;
  parameters `n_<axis>`, `<sym>_start/_step`, `<sym>` for stepped-axis or const symbols, `shots`).
- **Protocols + twins + conformance** (ADR 0016/0017): unchanged except `SimulatedSequencer` emits a 1-D
  result as one frame.
- 143 L0 tests + 2 tutorials; check_all green.

## In flight
- Nothing uncommitted. PR against `main` open for this session; human merges.

## Known broken / not yet real
- `test_wire_path_keeps_design_target_line_rate` is wall-clock bound: fails on the 4-vCPU cloud container
  (≈ 0.8–1.0×10⁶ pts/s vs the 10⁶ floor), passes on GitHub runners. Decide advisory treatment (cf. ADR 0014).
- `qdt-sim` not started: `SimulatedDevice` must implement `Sequencer` for backend `simulated` by
  interpreting the emitted body (sequence JSON, `symbols` map, `reduce`) against the dot model; until then
  stage results are the flat loop index.
- Flight Deck `live` source: feed `Executor.run()` to `StreamServer`; display reduction over `repeat`.
- QUA emitter (Step 5, `[opx]`): must validate 4 ns timing and map symbols to int input streams.
- Scope captures per stepped point (`WaveformSense` in a sweep) deferred (ADR 0019).
- Probe 01 scope half unrun → Step 5 input. Flight Deck: no axes/colorbar/cursors/zoom; first Dataset
  only. Server history unbounded (Step 6). `FINISH_LINE.md` TODO (human). `BENCH.md` skeleton; DUT #10.

## Next action
**Human:** merge the open PR, check CI.
**Then** a session on `qdt-sim`: import `quantum_dot_sim`, expose `DoubleDotValley` as `SimulatedDevice`
implementing `Sequencer` (interpret the `simulated` body: levels at `measure` time → sensor current via the
dot model; shots add noise; `reduce` honoured) and `LevelSource`/`LevelSense` for DC gates; a committed
scenario fixture and the L0 "reproduces within tolerance" test; then the Flight Deck `live` source
(`StreamServer.feed(Executor.run())`) and a stability diagram live, which closes the first exit criterion.

## Decisions pending (see plan §12)
- #10 surrogate DUT design — by Step 5 entry. #2 `payload_hdf5` location — Step 3.
- Whether the stream line-rate test becomes advisory off hardware (see Known broken).
