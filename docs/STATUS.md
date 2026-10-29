# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** is DONE (pull request #151 merged,
ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6c/simulated-stand-guide` (pull request against `main`; the human merges).
**Last session:** 2026-10-29 (session 36), no bench.

## Done this session
- **`docs/guides/simulated-stand.md`**, the human's request. It is a how-to that GitHub renders, explaining how
  to start the simulated stand (Phantom's device) and drive it from Flight Deck.
  - It covers starting the stand, a stability diagram with its charge transitions, the sensor's Coulomb
    diamonds, moving the operating point, the four-node tune-up, the run options and troubleshooting.
  - Every step was run in a browser against the demo server, and the eight screenshots in
    `docs/guides/img/` come from that run (quantized to 256 colours, 580 KB in all).
  - It is linked from `README.md`, `docs/index.md` and the MkDocs navigation.
- **`scripts/demo_control_path.py`'s printed walkthrough** now gives the Phantom device's windows. It
  still gave qdt-sim's windows and the retired `sensor_width_v` option, which #151 missed.
- **#152** (found-by-agent): the capture end-to-end test once timed out waiting for the "replaying" message.
  It passed on the rerun and on the pull request's run of the same commit.

## In flight
- The pull request for `step-6c/simulated-stand-guide` awaits the human's merge; it is watched.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #150, #152, #130, #122, #120, #119. The Sweep form still opens at qdt-sim's 0.03–0.18 V
  window; the guide warns about it, and no issue asks to change it yet.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** back to Step 6c. Work deliverable 11 (#76), then 14 (#112), then 15 (#114), on a branch
`step-6c/<short-name>`.
**Human:**
- Merge this pull request (the guide).
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
- **2026-10-29 (session 36):** "Can you write some docs that render in the GitHub that explain how to start the
  simulated stand and control it with flight deck?" → `docs/guides/simulated-stand.md`.
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
