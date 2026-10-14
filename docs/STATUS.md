# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (NOT STARTED).
Step 4b DONE (ADR 0036, PR #20 merged).
**Branch:** `step-4b/chopped-readout` (PR against `main` open). This is a follow-up to the human's demo
of Step 4b. `main` is the only other branch.
**Last session:** 2026-10-14. It acted on the human's demo feedback:
- abort works;
- assigning levels was confusing, and a number typed over `v_P2` gave a raw 422;
- there was no way to do a chopped readout.

## Step 4b exit criteria — met (DONE, ADR 0036; unchanged by this follow-up)
| Criterion | State |
|---|---|
| fresh browser + `qdt-server` only: craft, run, watch, record, analyse, overlays — e2e in CI and a scripted demo | ✔ `apps/flightdeck/e2e/control.test.ts` now also builds a chop and views `a − b`; `scripts/demo_control_path.py` |
| `control.py` frozen with ADR | ✔ ADR 0036 |

## Done
- Steps 0–4b DONE. ADR 0001–0037. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037), identity/envelope/`qdt-hdf5-v1` (0028),
  modeling (0033), control (0036).
- **This session:**
  - **Editor fix:** a number typed over the swept symbol now gets a live editor error ("the inner axis P2
    is not used…"). Server 422s read as messages (`describeDetail`). Each symbol cell shows its binding
    (`level ← P2 (swept)`), and a note says a pulse level adds to DC, holds, and resets each shot.
  - **Chopped readout (ADR 0037):**
    - `Affine` values: `v_P2 + 0.002`, `-v_P2`, `0.5*v_P2 - 1e-3`.
    - A `difference` primitive: `result = a − b` per shot, before reduction, recorded beside `a` and `b`.
    - Both are additive union members with no version bump, because the registry recomputes the
      definition hash on ingest. `test_hashed_fixture_reserializes_unchanged` pins this.
    - The emitter, simulator, exports, editor and tests are all in one commit.
    - The editor's primitive list now derives from the generated union, so a new primitive fails `tsc`.
  - **View:** a `variable` picker (only the first variable could be viewed before), and `minus`, which
    shows `a − b` of two same-shape variables client-side.
- 282 Python tests (+5 Postgres-parametrized), 65 Flight Deck unit tests, 4 e2e.

## In flight
- Nothing uncommitted. The PR for `step-4b/chopped-readout` awaits review.

## Known broken / not yet real
- **No operating point.** A sweep cannot set fixed DC levels on gates it doesn't sweep. In a stage sweep
  the inner gate's DC sits at whatever it was, which is 0 in the simulator, so pulse levels look
  absolute. Step 5 hardware needs this; it is a `SweepDefinition` addition (ADR-level, and mind the
  hash rule in ADR 0037).
- **The form can't hold the inner gate fixed.** A stage sweep always pulses its inner axis.
- **Simulator `drive`:** passes time with no effect, and `ramp` jumps to its end level. There is no QUA
  emitter yet; it must implement `Affine` and `difference` (ADR 0037).
- **Diamond estimator:** needs a cold sensor (ADR 0030). The lattice estimate needs a periodic window.
  The dot model's zero-clipping is unresolved (ADR 0020).
- **Overlays:** drawn in one colour. The Postgres suite is not run locally (no docker); CI runs it. Two
  wall-clock CI gates flake.
- Carried over:
  - the server payload store is a directory (ADR 0026);
  - `FINISH_LINE.md` TODO (human);
  - `BENCH.md` is a skeleton;
  - on Windows, run pnpm as `corepack pnpm` in `apps/flightdeck`.

## Next action
**Human:**
1. Try the chop in the demo (`uv run python scripts/demo_control_path.py`; the walkthrough lists the
   five rows) and merge the PR.
2. Decide whether a sweep's **operating point** (fixed DC levels on unswept gates) comes before Step 5
   or as its first session.
3. Settle **#10**, the surrogate DUT design. It gates Step 5.

**Then** the first Step 5 session:
1. Record #10 by ADR, plus the operating point if chosen.
2. Fill in `docs/BENCH.md`.
3. Start the first real driver with `/add-driver` (`packages/qdt-lab/CLAUDE.md`), passing the
   conformance suite under `-m hardware`.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. Multi-record analyses deferred. Results may
  carry arrays (ADR 0031). The control path came before the drivers (ADR 0032).
- **2026-10-14:** a chopped readout's difference is recorded, not only displayed (ADR 0037).

## Decisions pending
- #10 surrogate DUT design (by Step 5 entry).
- Operating point: where and when.
- Advisory treatment of the two wall-clock CI gates.
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
