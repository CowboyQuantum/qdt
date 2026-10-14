# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 5 — Instrument drivers → `docs/steps/05-instrument-drivers-last-mile.md` (NOT STARTED).
Step 4b DONE (ADR 0036). The demo follow-ups are merged: #21 (ADR 0037), #22 (ADR 0038), #23 (ADR
0039).
**Branch:** `step-5/surrogate-dut-draft` (PR #24). It closes #10 with ADR 0040: no surrogate DUT
board; L2 is instrument-on-instrument.

**Last session:** 2026-10-14.
- The human agreed ADR 0037 (no version bump; `difference` in the sequence).
- They asked for the operating point before Step 5 (built as ADR 0038).
- They chose advisory wall-clock CI gates (ADR 0039).
- After a surrogate DUT board was drafted, they asked to skip it. L2 now uses the instruments
  themselves plus a bias tee (ADR 0040).

## Step 4b exit criteria — met (DONE, ADR 0036; unchanged by the follow-ups)
| Criterion | State |
|---|---|
| fresh browser + `qdt-server` only: craft, run, watch, record, analyse, overlays — e2e in CI and a scripted demo | ✔ `apps/flightdeck/e2e/control.test.ts` (now also chop, `a − b`, operating point); `scripts/demo_control_path.py` |
| `control.py` frozen with ADR | ✔ ADR 0036 |

## Done
- Steps 0–4b DONE. ADR 0001–0040. Frozen: `Dataset` (0015; v2 by 0031), protocols (0021),
  stand/activity/pulse (0022; amended additively by 0037 and 0038), identity/envelope/`qdt-hdf5-v1`
  (0028), modeling (0033), control (0036).
- **PR #21 (ADR 0037):**
  - editor fix for a number typed over the swept symbol, and readable 422s;
  - `Affine` values (`v_P2 + 0.002`);
  - the `difference` primitive (`dI = I_on − I_off` per shot, recorded);
  - the `variable` and `minus` view pickers.
- **This branch (ADR 0038):** `SweepDefinition.levels`, fixed DC levels set once before the scan and
  held.
  - The field is excluded from the dump when empty, so existing hashes are unchanged.
  - Compile resolves each level as `level_source`, and the executor sets them first.
  - The panel has an "operating point" section, checked live against the swept channels.
  - The simulator test pins "pulse adds to DC".
- **ADR 0039 (supersedes 0014):** wall-clock rate targets are advisory on shared CI runners, with a
  floor at half the target.
  - The bench takes `--rate-advisory`.
  - The Python rate tests use a `wallclock_rate` fixture: strict locally, advisory with
    `QDT_WALLCLOCK_ADVISORY=1`, which CI sets.
- 287 Python tests (+5 Postgres-parametrized), 68 Flight Deck unit tests, 4 e2e.

## In flight
- **ADR 0040 (closes #10):** L2 = instrument-on-instrument.
  - L2-1: QDAC DC × OPX pulse through the bias tee, read by the stage `measure`; a plane fit with
    iso-line overlays. This is the Step 5 exit run.
  - L2-2: QDAC and SMU current readout into the scope's 1 MΩ input.
  - L2-3: the bias tee's droop, a single-exponential fit.
  - Updated to match: `docs/BENCH.md` § L2, plan §7.1 and #10, every step file's L2 heading, Step 5's
    deliverables, tests and exit, the `CLAUDE.md` pointer and `bench/README.md`.

## Known broken / not yet real
- **The form can't hold the inner gate fixed:** a stage sweep always pulses its inner axis. With an
  operating point, sweep its pulse around the held DC level.
- **Simulator `drive`:** passes time with no effect, and `ramp` jumps to its end level. There is no QUA
  emitter yet; it must implement `Affine` and `difference` (ADR 0037).
- **Diamond estimator:** needs a cold sensor (ADR 0030). The lattice estimate needs a periodic window.
  The dot model's zero-clipping is unresolved (ADR 0020).
- **Overlays:** drawn in one colour. The Postgres suite is not run locally (no docker); CI runs it.
- Carried over:
  - the server payload store is a directory (ADR 0026);
  - `FINISH_LINE.md` TODO (human);
  - `BENCH.md`: instrument models and the L2 specs are still TODO (human);
  - on Windows, run pnpm as `corepack pnpm` in `apps/flightdeck`.

## Next action
**Human:**
1. Merge PR #24.
2. Fill in `docs/BENCH.md`: the instrument models, and § L2 "To fill in" (bias tee specs; the L2-1 load
   check; QDAC current range; scope input spec). Real addresses go in `CLAUDE.local.md`, not the repo
   (rule 7).

**Then** the first Step 5 session:
1. Open Step 5. Start with the two curated fits L2 needs (plane with iso-line overlays; single
   exponential): pure, testable at L0 now, before any hardware.
2. Fill in `docs/BENCH.md`.
3. Start the first real driver with `/add-driver` (`packages/qdt-lab/CLAUDE.md`), passing the
   conformance suite under `-m hardware`.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. Multi-record analyses deferred. Results may
  carry arrays (ADR 0031). The control path came before the drivers (ADR 0032).
- **2026-10-14:**
  - a chop's difference is recorded (ADR 0037);
  - additive changes without a version bump are accepted (ADR 0037);
  - the operating point comes before Step 5 (ADR 0038);
  - wall-clock CI gates are advisory, option A (ADR 0039).

## Decisions pending
- A default operating point per device (not in ADR 0038).
- Whether to fix the dot model's zero-clipping (ADR 0020 amendment).
- Whether the diamond estimator should survive warm edges.
