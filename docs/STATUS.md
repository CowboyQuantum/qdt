# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 2 — Experiments over a simulated device → `docs/steps/02-experiments-over-simulated-device.md`
**Branch:** `claude/session-plan-review-wudauu` (session-assigned name; restarted from `main` after PR #1 merged.
Human merges to `main`; pushing `main` stays manual)
**Last session:** 2026-10-12 — session (8), first Step 2 commit: capability protocols renamed to the
Level/Waveform × Source/Sense grid plus `Sequencer` (ADR 0016); quantity moved onto `ChannelMap`.

## Step 2 exit criteria
| Criterion | State |
|---|---|
| `SweepDefinition` round-trips and runs on `SimulatedDevice`, live in Flight Deck | ✘ |
| stand + activity slices frozen with ADR | ✘ (`stand.py` has `ChannelMap` with `quantity`; `activity.py` not started) |
| Protocols frozen with ADR (the second deliberate freeze, ADR 0007) | ✘ naming fixed (ADR 0016); 1 of 5 protocols exists |

## Done
- Step 0, Step 1 DONE. ADR 0001–0016. Contract frozen (ADR 0015). CI green on `main` at 4bfd48f.
- **Protocol naming (ADR 0016):** `LevelSource`, `LevelSense`, `WaveformSource`, `WaveformSense`, `Sequencer`.
  `SourceMeasure` dropped (SMU = `LevelSource` + `LevelSense` on one terminal). Methods are `set`/`get`;
  the quantity (voltage/current) is `ChannelMap.quantity`. `LevelSource` + `SimulatedLevelSource` +
  conformance (`tests/test_conformance_level_source.py`, fixture `level_source`) exist. Tutorial 00 updated.
- `qdt_lab/stream/`, `apps/flightdeck`, Probe 01 OPX half: see ADR 0010–0015; unchanged this session.

## In flight
- Nothing uncommitted. Branch ahead of `main` by this session's commit; human to merge and push.

## Known broken / not yet real
- `test_wire_path_keeps_design_target_line_rate` (stream, ≥ 10⁶ pts/s over localhost) is wall-clock bound: on
  the 4-vCPU cloud container it fails ~2 of 3 runs at ≈ 0.8–0.9×10⁶; passes on GitHub runners and on hardware.
  Same class as the latency gate in ADR 0014. Not touched this session; decide whether it gets the same
  advisory treatment.
- Four protocols not yet defined: `LevelSense`, `WaveformSource`, `WaveformSense`, `Sequencer`. Method
  signatures are open; `Sequencer` must expose the Probe 01 constraints (int runtime parameters, positional
  results). Executor must refuse one terminal in two roles per plan step (ADR 0016).
- Probe 01 scope half unrun → Step 5 input (LAB_GUIDE step 5, ~10 min, no OPX).
- Flight Deck: no axes/colorbar/cursors/zoom; first Dataset only. Server history unbounded (Step 6).
- `FINISH_LINE.md` TODO open (human). `docs/BENCH.md` skeleton; surrogate DUT not built (#10, by Step 5).

## Next action
**Human:** merge this branch to `main`, push, check CI.
**Then** a session on `step-2/protocols` defines the four remaining protocols with the human's sign-off on
signatures (start with `LevelSense` and `WaveformSense`, which the stability-diagram sweep needs first), each
with a `Simulated*` twin and conformance tests, then `qdt-sim`'s `SimulatedDevice` behind them. `activity.py`
(`SweepDefinition`, `ExecutionPlan`) comes after the protocols; its QUA payload slot is int-only (ADR 0015).

## Decisions pending (see plan §12)
- #10 surrogate DUT design — by Step 5 entry. #2 `payload_hdf5` location — Step 3.
- Whether the stream line-rate test becomes advisory off hardware (see Known broken).
