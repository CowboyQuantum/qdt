# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6d — The Phantom cutover** (`docs/steps/06d-phantom-cutover.md`), IN PROGRESS, inserted
this session beside Step 6c by ADR 0087. Deliverables 1–3 (#141) are done in L0. Step **6c — Lab deployment**
(`docs/steps/06c-lab-deployment.md`) stays IN PROGRESS: its remaining work waits on the bench and on the human's
decisions, and the two steps interleave. Steps 0–6 and 6b are DONE.
**Branch:** `step-6d/cutover-plan-and-interpreter` (pull request against `main`; the human merges).
**Last session:** 2026-10-28 (session 34), no bench.

## Done this session
- **The cutover has a home in the plan.** ADR 0087 inserts Step 6d. Phantom becomes a dependency of `qdt-sim` and
  of nothing else, pinned by the git tag `v0.2.0` (commit `f72daac`), with only `phantom.api` imported. The seam
  is a protocol in qdt-lab. ADR 0020's model is superseded when #140 merges, not before. A pin moves in a pull
  request of its own. The step file lists 14 deliverables; the steps index, plan §7.2 and the ADR index carry
  the new row.
- **#141, the sequencer interpreter, now lives in `qdt_lab.simulated.SimulatedInstrument`.**
  - The interpreter covers channels and roles, the bias tee's sum, triggered lists, captures, shot reduction
    and stream frames.
  - It runs over a `SimulatedPhysics` protocol: named inputs, one output, a default level per input, a clock
    the physics owns, and the two calls `hold` and `sense`.
  - `LinearPhysics` is the protocol's test double. The level-source and triggered-level-source conformance
    suites now run on it, and `packages/qdt-lab/tests/test_simulated_instrument.py` runs an emitted shot
    through the real compile and execute path.
  - `qdt_sim.device` is now `DoubleDotPhysics` plus a `SimulatedDevice` subclass with the same constructor,
    attributes and error messages. It went from 479 lines to 150.
- **Bit-identity proven.**
  - A pytest plugin hashed every `sense` value, every frame and every clock reading across the qdt-sim,
    qdt-server, qdt-analysis and tutorial suites: 35,416 readings in 55 tests. The run with the old class and
    the run with the new one hash equal.
  - The stability fixture and the seven `SimResult` fixtures regenerate identically from both classes, so none
    was regenerated.
  - Regenerating on this machine differs from the committed files only in the last few bits (at most
    7×10⁻¹⁵ relative). That is cross-platform rounding, within the package's stated `rtol=1e-9`.
- `uv run pytest`: 543 passed. `bash scripts/check_all.sh`: green.

## In flight
- The pull request for `step-6d/cutover-plan-and-interpreter` awaits the human's merge; it is watched.
- **#140 and #142 (step deliverables 4–14), one pull request against `v0.2.0`.** Nothing blocks it. The tag
  exists, and `CowboyQuantum/phantom` is public, so qdt's CI can fetch it without a token.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #130, #122, #120, #119.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** Step 6d deliverables 4–14 (#140 with #142), on a branch `step-6d/<short-name>`. Work in
this order:
1. Add Phantom from `git+https://github.com/CowboyQuantum/phantom` at tag `v0.2.0` as a dependency of `qdt-sim`.
   Extend `scripts/check_imports.py` to fence it: no `phantom` import outside `qdt-sim`, and none but
   `phantom.api` there.
2. Implement `SimulatedPhysics` over a Phantom `Session`, with the truth tests need (`lattice_truth`,
   `sensor_truth`) read from `Device.truth()`.
3. Commit the device files with their recipes and the script that compiles them, and give `SimScenario` its
   device reference (name and SHA-256) with a migration.
4. Build the simulated stand from the device, and replace the run options.
5. Regenerate every simulator fixture once, delete `dot.py` and `noise.py`, and run `python -m phantom.contract`
   in CI.

Write the ADR that freezes the `SimScenario` change, and decide in it what a stored v1 scenario becomes.
Read Analysis 0007 and Phantom's `docs/CONTRACT.md` at the tag first.
If the human sends the session to Step 6c instead: deliverables 11 (#76), 14 (#112) and 15 (#114).
**Human:**
- Merge this pull request.
- Decide #147, the two oracles of the L2 rows.
- On `qdt-db`, run `uv run python -m qdt_registry init` as the administrator.
- Run `bench/test_l2_orchestration.py` on the bench with `QDT_STAND_FILE` set.
- Still open from earlier sessions:
  - Send plan §9 to IT.
  - Send the `ipconfig` output for #80.
  - Decide ADR 0077 before Step 6c deliverables 9 and 10.
  - Put the runbook on the lab computer.
  - Write the pre-deployment records.
  - Run restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
- **2026-10-28 (session 34):** "Phantom cutover now. The tag 0.2.0 has been made" → ADR 0087, Step 6d, #141.
- **2026-10-28 (session 33):** "Go ahead, but I also didn't realize we drifted off the phantom cutover. Once you
  finish your next task, tell me what's stopping you from completing #140-142."
- **2026-10-27 (session 32):** "I will re init the register when I get back to the database pc. Start
  deliverable 8."
- **2026-10-27 (session 31):** "Ok then continue with deliverable 7." After #144 was opened: "Yes, make sure
  all agent submitted PRs have a watcher armed going forward" → root `CLAUDE.md`, End step 6.
- **2026-10-27 (session 30, detour):** on Analysis 0007: "move the sequencer interpreter into qdt lab as you
  say. device file makes more sense. Let's hold off on deciding the release cadence. I don't see a decision
  needed for the simulated stand."
- Earlier direction, verbatim: `git show f748fe2:docs/STATUS.md` and `git show d7c7a01:docs/STATUS.md`,
  § Direction recorded, and `git show b94193f:docs/STATUS.md` (sessions ≤ 25).

## Decisions pending
- All `decision` issues (`gh issue list --label decision`), now including #147, the two L2 oracles.
- Step 6c's ADR 0077, needed before deliverables 9 and 10 (#80).
- Held by the human: the cadence of Phantom releases against qdt's pin (Analysis 0007, answer 3).
- Decided with #142, in its ADR: what a stored `SimScenario` v1 becomes.
