# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 2 — Experiments over a simulated device → `docs/steps/02-experiments-over-simulated-device.md`
**Branch:** `claude/session-plan-review-wudauu` (session-assigned name; restarted from `main` after PR #2 merged.
Every session ends with a PR against `main`; the human merges)
**Last session:** 2026-10-12 — session (9): all five capability protocols defined with signatures (ADR 0017),
`Simulated*` twins, and conformance suites; `SequencerProgram` envelope added to `activity.py`.

## Step 2 exit criteria
| Criterion | State |
|---|---|
| `SweepDefinition` round-trips and runs on `SimulatedDevice`, live in Flight Deck | ✘ not started |
| stand + activity slices frozen with ADR | ✘ `stand.py`: `ChannelMap` (+ `quantity`, `settle_s`, `integration_s`). `activity.py`: `SequencerProgram` only; `SweepDefinition`, `ExecutionPlan` next |
| Protocols frozen with ADR (second deliberate freeze, ADR 0007) | ✘ all five defined (ADR 0016 names, ADR 0017 signatures); freeze ADR at exit |

## Done
- Steps 0–1 DONE. ADR 0001–0017. Contract frozen (ADR 0015). CI green on `main` at 5369126.
- **Protocols** (`qdt_lab/protocols/`): `LevelSource` set/get, `LevelSense` sense, `WaveformSource`
  play/stop, `WaveformSense.arm(channel, dataset, variable) -> Source`, `Sequencer.compile(program)` +
  `run(compiled, int params, dataset) -> Source`. Producers are handed the Dataset and return a stream.
- **Twins** (`qdt_lab/simulated/`): `level.py`, `waveform.py`, `sequencer.py`. `SimulatedLevelSense` follows
  a paired source (L0 loopback). `SimulatedWaveformSense` fills records on the declared `LinearCoordinate`.
  `SimulatedSequencer` ignores the body and fills results with the flat loop index (Probe 01's oracle).
- **Conformance** (`packages/qdt-lab/tests/test_conformance_*.py`, fixtures in `conftest.py`): one suite per
  protocol; real backends register in the fixture lists. `FLAT_INDEX_PROGRAM` is the sequencer conformance
  program; a real sequencer registers its own body for it.
- **Schema:** `activity.py` `SequencerProgram` (`SequencerParameter` name/unit/scale, `SequencerResult`
  name/dims-by-parameter/dtype/unit, opaque `body`, `backend`) with `check_parameters`, `result_shape`,
  `check_run`. 109 tests + check_all green.

## In flight
- Nothing uncommitted. PR against `main` open for this session; human merges.

## Known broken / not yet real
- `test_wire_path_keeps_design_target_line_rate` is wall-clock bound: fails ~2/3 on the 4-vCPU cloud
  container (≈ 0.8×10⁶ pts/s vs 10⁶), passes on GitHub runners. Decide advisory treatment (cf. ADR 0014).
- Executor does not exist: nothing yet honours `settle_s`/`integration_s` or refuses one terminal in two
  roles per plan step (ADR 0016/0017 "must now").
- `qdt-sim` package not started; `SimulatedDevice` (double-dot physics behind the protocols) is next after
  the activity slice.
- Probe 01 scope half unrun → Step 5 input. Flight Deck: no axes/colorbar/cursors/zoom; first Dataset
  only. Server history unbounded (Step 6). `FINISH_LINE.md` TODO (human). `BENCH.md` skeleton; DUT #10.

## Next action
**Human:** merge the open PR, check CI.
**Then** a session on the activity slice: `SweepDefinition` (axes as `LinearCoordinate`s over `ChannelMap`
logical channels, the sensed variables, and for a sequencer-driven inner loop a `SequencerProgram` plus the
mapping from axis to integer parameter via `scale`) and `ExecutionPlan`; then `qdt_lab/experiment/` compiler
(definition → plan + Dataset) and executor (plan → protocol calls → `Source`; honours `settle_s`; refuses a
terminal in two roles). L0 tests per the step file: dry-run point count/order/shape, reproducibility.
`qdt-sim` `SimulatedDevice` and the Flight Deck `live` source follow.

## Decisions pending (see plan §12)
- #10 surrogate DUT design — by Step 5 entry. #2 `payload_hdf5` location — Step 3.
- Whether the stream line-rate test becomes advisory off hardware (see Known broken).
