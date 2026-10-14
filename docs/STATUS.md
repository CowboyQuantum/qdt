# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (NOT STARTED).
Step 4b DONE (ADR 0036), pending the human's merge of PR `step-4b/pulse-editor`.
**Branch:** `step-4b/pulse-editor` (PR against `main` open). `main` is the only other branch.
**Last session:** 2026-10-13, Step 4b session 3. It closed Step 4b: the pulse-sequence editor, 1-D
sweeps, abort, the one-process demo, and the `control.py` freeze.

## Step 4b exit criteria — all met (DONE, ADR 0036)
| Criterion | State |
|---|---|
| fresh browser + `qdt-server` only: craft sweep + pulse sequence, run, watch, record, analyse, overlays — e2e in CI and a scripted demo | ✔ `apps/flightdeck/e2e/control.test.ts` (adds edit → bind → run, and a 1-D trace); `scripts/demo_control_path.py`. **The human has not walked the demo yet** |
| `control.py` frozen with ADR | ✔ ADR 0036 (v1 wire examples pinned in `packages/qdt-schemas/tests/test_control.py`) |

## Done
- Steps 0–4b DONE. ADR 0001–0036. Frozen: `Dataset` contract (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; `ExecutionPlan` v2 by 0031), identity/envelope/`qdt-hdf5-v1` (0028),
  modeling (0033), control (0036).
- **This session:**
  - **Editor** (ADR 0035, `apps/flightdeck/src/control/sequence.ts`): a form over `PulseSequence`.
    - One row per primitive, with number-or-symbol cells and bindings to an axis or a constant.
    - The columns are type-checked against the generated `api.ts`.
    - It refuses what the server's validators refuse, and the panel shows the errors live.
  - **1-D sweeps:** `stageSweep`/`dcSweep` take the edited sequence and allow no outer axis.
  - **Abort:** `POST /runs/{id}/abort`, plus an abort button on queued and running runs.
    - Queued: aborted at once. Running: stops between frames and is recorded as `aborted`.
  - **Demo:** `qdt-server --ui <dist>` serves the built UI at `/`; `scripts/demo_control_path.py`
    builds the UI if needed, runs the server and opens the browser.
- 274 Python tests (+5 Postgres-parametrized with `QDT_TEST_PG_DSN`), 57 Flight Deck unit tests, 4 e2e.

## In flight
- Nothing uncommitted. The PR for `step-4b/pulse-editor` awaits review.

## Known broken / not yet real
- **Diamond estimator:** needs a cold sensor (`sensor_width_v` 0.01). Warm edges make E_c come out
  ~30 % low (ADR 0030).
- **Lattice estimate:** needs a periodic window.
- **`DoubleDotModel.energies`:** zero-clipping creates duplicate states (an ADR 0020 amendment).
- **Simulator `drive`:** passes time with no effect, and `ramp` jumps to its end level (ADR 0035).
- **Sequence editor:** does not edit `call`/`Segment`s. New rows only default to `_pulse` lines; the
  channel choice is not limited to the stage instrument.
- **Overlays:** drawn in one colour, with no toggle.
- **Postgres suite:** not run locally (`docker` is not on PATH here). CI runs it.
- **Flaky CI gates:** two wall-clock-bound gates flake on shared runners. Their advisory treatment is
  undecided.
- Carried over:
  - model physics gaps (ADR 0020);
  - the QUA emitter (Step 5);
  - the server payload store is a directory (ADR 0026);
  - `FINISH_LINE.md` TODO (human);
  - `BENCH.md` is a skeleton;
  - on Windows, run pnpm as `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:**
1. Run `uv run python scripts/demo_control_path.py`. The walkthrough prints on start: stage sweep plus
   edited sequence, diamonds, 1-D, abort.
2. Merge the PR. Merging accepts the `control.py` freeze (ADR 0036).
3. Settle decision #10, the surrogate DUT design. It gates Step 5.

**Then** the first Step 5 session:
1. Read `docs/steps/05-…` and `docs/BENCH.md`.
2. Record #10 by ADR with the human and fill in BENCH.md's wiring and loopback map.
3. Start the first real driver with `/add-driver` (`packages/qdt-lab/CLAUDE.md`), as a vendor extra,
   passing the conformance suite under `-m hardware`.

## Direction recorded (human, 2026-10-13)
- The end state is a web app. Users run **curated** analyses from Flight Deck; there is no method
  authoring in the browser. Multi-record analyses are deferred. Results may carry arrays (ADR 0031).
- The control path came before the drivers (ADR 0032). Real drivers enter behind `RunManager`'s
  backends, and the API and UI do not change.

## Decisions pending
- #10 surrogate DUT design (by Step 5 entry).
- Advisory treatment of the two wall-clock CI gates.
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment; regenerates a fixture).
- Whether the diamond estimator should survive warm edges.
