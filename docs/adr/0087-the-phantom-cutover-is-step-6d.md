# 0087 — The Phantom cutover is Step 6d, beside 6c; Phantom is a dependency of `qdt-sim` alone, pinned by git tag

**Status:** Accepted
**Date:** 2026-10-28
**Step:** process (the plan's §7.2 order; issues #140, #141, #142)

## Context
Analysis 0007 (2026-10-27) laid out how Phantom, the device simulator in its own repository, replaces the
physics inside `qdt-sim`. The human answered its questions the same day: the sequencer interpreter moves
into qdt-lab; a scenario names a committed device file; the release cadence is held; no decision is
needed for Step 6c's simulated stand. Issues #140, #141 and #142 were filed, and each said the cutover
needs a home in the plan before any code (ADR 0071: work traces to a step file, an accepted ADR or a
labelled issue). No session wrote one, because every STATUS since named Step 6c's next deliverable; on
2026-10-28 the human noticed the drift and said: "Phantom cutover now. The tag 0.2.0 has been made."

Phantom's side is done: its Step 8 is merged, with qdt's six requests built (`phantom.api`, `Session`
with bias, noise seed, `hold` and stated samples, `Device.truth` under qdt's names, `Device.knowable`,
`python -m phantom.contract`), and `v0.2.0` is tagged at `f72daac`. Step 6c's remaining work is mostly
bench sessions and human decisions (the T-rows, W-1, ADR 0077, #147); the cutover is software only.

## Decision
1. **Insert Step 6d — the Phantom cutover** (`docs/steps/06d-phantom-cutover.md`) beside Step 6c, as ADR
   0073 inserted 6c. The two interleave: 6c's bench rows need the human at the bench, 6d needs only a
   session. STATUS names which one the next session works on. Steps 7 and 8 keep their numbers.
2. **Phantom is a dependency of `qdt-sim` and of nothing else**, pinned by git tag: the workspace takes
   `phantom` from `git+https://github.com/CowboyQuantum/phantom` at `v0.2.0`, and `uv.lock` records the
   commit. Never the Python Package Index (plan §10). Only `phantom.api`, Phantom's one consumer surface,
   is imported, and only inside `qdt-sim`; `scripts/check_imports.py` enforces both when the dependency
   lands.
3. **The seam is a protocol in qdt-lab**, `qdt_lab.simulated.SimulatedPhysics` (Analysis 0007 §3): the
   instrument behaviour (channels and roles, the bias tee's sum, the sequencer interpreter, triggered
   lists, captures, shot reduction, stream frames) lives in qdt-lab; `qdt-sim` implements the physics,
   first over its own model (#141, which changes no output), then over a Phantom `Session` (#140).
4. **Order:** #141 first; then #140 and #142 in one pull request against the tag, because only Phantom
   produces device files. When that pull request merges, ADR 0020's model and noise decisions are
   superseded, and its status line says so then; its other decision (a simulated device behind the
   capability protocols) lives on in qdt-lab's instrument.
5. **ADR 0078 (proposed) and the physics core.** Its boundary table puts the physics core "inside qdt
   behind an enforced seam". Phantom is outside qdt, a repository and a release of its own, and the seam
   is this protocol plus the import fence. That is recorded here as the fact for ADR 0078's eventual
   acceptance; a proposed ADR is not edited.
6. **A pin moves in a pull request of its own**, which regenerates every simulator fixture and says which
   Phantom changes caused which differences. How often is the human's open decision.

## Consequences
- Easier: the work that drifted has a step file a session can follow; Phantom's physics (eight gates,
  disorder, valley, spin, dynamics) reaches qdt without qdt owning it; qdt-lab can test its simulated
  instrument without importing `qdt-sim`.
- Harder: qdt's CI fetches Phantom from GitHub at the tag; every committed simulator output changes once
  at the cutover and again at every pin bump; a fourth lettered step sits in the order.
- Must now: `docs/steps/README.md` and plan §7.2 list 6d; the step's L0 rows land with #141, #140 and
  #142; `qdt-sim`'s `CLAUDE.md` describes the adapter once it is one.

## Alternatives considered
- Run the cutover after Step 6c — rejected by the human (2026-10-28), and 6c's remainder waits on the
  bench anyway.
- Copy Phantom's modules into qdt — rejected: two sources of the same physics, and Phantom's own tests and
  contract would not follow the copy.
- A git submodule — rejected: uv's git dependency with a locked commit pins the same thing with one
  mechanism the workspace already uses for every other dependency.
- Publish Phantom to the Python Package Index — rejected by plan §10 (no public package index).
