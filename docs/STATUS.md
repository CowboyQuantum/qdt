# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** (`docs/steps/06d-phantom-cutover.md`)
is DONE in L0 once this session's pull request is green (ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6d/phantom-adapter` (pull request against `main`; the human merges).
**Last session:** 2026-10-28 (session 35), no bench.

## Done this session
- **#140 and #142: `qdt-sim` is an adapter over Phantom `v0.2.0`** (ADR 0088, which supersedes ADR 0020).
  - Phantom is a git dependency of `qdt-sim` alone, pinned by the tag (`uv.lock` records `f72daac`), and
    reached only through `phantom.api`. `scripts/check_imports.py` enforces both.
  - `PhantomPhysics` is one Phantom session per run, behind the `SimulatedPhysics` protocol from #141. The old
    model (`dot.py`) and noise models (`noise.py`) are deleted. `qdt-sim` is 295 lines, and a test pins it
    under 300.
  - Two committed device files, `two-dot-sige-a` and `two-dot-sige-b` (one layout, disorder draws 2 and 5),
    live in `packages/qdt-sim/src/qdt_sim/devices/`. Only `scripts/make_sim_devices.py` writes them, compiling
    from `qdt_sim/recipes.json`, and `qdt_sim.scenarios.DEVICES` pins their SHA-256 hashes.
  - `scripts/check_all.sh` now recompiles the recipes (`make_sim_devices.py --check`) and runs
    `python -m phantom.contract` on every device file, which takes about 4 s.
  - `SimScenario` v2 names a device file and its hash; `seed` is the noise seed. There is no migration,
    because neither `SimScenario` nor `SimResult` is persisted.
  - The simulated stand has a channel for each of the device's eight gates, plus the pulse lines, the bias
    and the sensor.
  - The run options are `seed`, `noise` and `device`, and the server checks a scenario's hash.
  - The registered device carries Phantom's version, its model versions and the file's hash.
- **Tune-up windows are now the stand's.** The old node windows were sized for qdt-sim's toy device and
  cannot find Phantom's, whose plungers sit near 0.6 V at about 20 electrons per volt and whose sensor peaks
  are 1 V apart.
  - `qdt_tuning.TEMPLATES` take windows per node, and `Settings.nodes` holds them.
  - The simulated stand's windows (`SIMULATED_NODES`) sit about the programmed point, at 10 ms per lattice
    pixel, because Phantom's readout noise is physical.
  - A real stand gives no windows, so its nodes keep the constructors' defaults.
- **Fixtures regenerated.** The stability fixture and the seven tune-up fixtures were regenerated, and the
  `cold-sensor` scenario became `second-device`. Every tune-up is accepted on both devices. Tolerances against
  truth now scale with the device, and ADR 0088 §9 gives the reasons.
- **Tests moved to Phantom's truth.** The analysis, tutorial and Flight Deck end-to-end tests take their truth
  from `Device.truth` and `Device.at`. The diamond overlays are checked against the edge mask as well,
  because the warm sensor blurs the edges where neighbouring diamonds cross.
- **#150** (found-by-agent, decision): click-to-set on a pulsed axis sets the DC line to the pulse offset. That
  was right only while the DC level sat at 0 V, which no longer holds.
- Checks: `uv run pytest` 534 passed; `bash scripts/check_all.sh` green; Flight Deck unit tests (151) and
  end-to-end tests (17) green; the L2 rows' simulated mode as before (T-1, T-2 and T-7 pass).

## In flight
- The pull request for `step-6d/phantom-adapter` awaits the human's merge; it is watched.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #150, #130, #122, #120, #119.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** back to Step 6c. Work deliverable 11 (#76), then 14 (#112), then 15 (#114), on a branch
`step-6c/<short-name>`.
**Human:**
- Merge this pull request.
- Decide #150 (click-to-set on a pulsed axis) and #147 (the two L2 oracles).
- On `qdt-db`, run `uv run python -m qdt_registry init` as the administrator.
- Run `bench/test_l2_orchestration.py` on the bench with `QDT_STAND_FILE` set.
- If you want a cold-sensor scenario back, ask Phantom for a compile parameter for the sensor's peak width.
  Phantom `v0.2.0` fixes it at 0.04 V of sensor potential, whatever the temperature.
- Still open from earlier sessions:
  - Send plan §9 to IT.
  - Send the `ipconfig` output for #80.
  - Decide ADR 0077 before Step 6c deliverables 9 and 10.
  - Put the runbook on the lab computer.
  - Write the pre-deployment records.
  - Run restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
- **2026-10-28 (session 35):** after #149 merged and was offered as next: "Start this" → #140 and #142.
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
- All `decision` issues (`gh issue list --label decision`), now including #150 (click-to-set on a pulsed
  axis) and #147 (the two L2 oracles).
- Step 6c's ADR 0077, needed before deliverables 9 and 10 (#80).
- Held by the human: the cadence of Phantom releases against qdt's pin (Analysis 0007, answer 3). Each pin
  bump is its own pull request (ADR 0087).
