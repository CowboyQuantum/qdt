# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** is DONE (pull request #151 merged,
ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6c/sweep-held-point` (pull request against `main`; the human merges).
**Last session:** 2026-10-29 (session 36, continued), no bench.

## Done this session
- **Merged earlier today:** the simulated-stand guide (#153); the device-file check's tolerance, which fixed
  #154 and arrived through #153, so #155 was closed as redundant; and the diagnostic for #152 (#156).
- **#157, the human's request: the Sweep form opens about where the stand sits.**
  - Each stepped axis opens 0.3 V wide, centred on its channel's held level, or on the instrument's setpoint
    when nothing is held. Both come from `GET /levels/state`. A pulse line reports 0, so it opens about 0.
  - The form centres an axis again when its channel changes or Levels changes a level (`levels:changed`).
  - An axis whose start or stop the user typed is never moved again.
  - **add level** starts the new row at its channel's level instead of 0.
  - The pure parts are `sittingLevels` and `centredWindow` in `src/control/sweeps.ts`, with unit tests. The
    control end-to-end test checks that the form opens at 0.45–0.75 V on `P1` and ±0.15 on `P2_pulse`.
- **#158, the human's request: `pnpm screenshots`** (`apps/flightdeck/scripts/screenshots.mjs`) regenerates
  the guide's eight pictures.
  - It builds Flight Deck, starts its own `qdt-server` on an empty registry and free ports, and walks the
    guide's steps in headless Chrome. It takes about 30 seconds.
  - It stops with an error on any step that does not complete, and then writes no picture.
  - It quantizes the pictures with a pinned Pillow (`pillow==12.3.0`) that `uv run --with` fetches for that
    command alone. Pillow is not a workspace dependency, so `uv.lock` does not change.
  - The guide's pictures were retaken with it (537 KB in all), and the guide now describes the new windows
    and how to rerun the script.
- Checks: `uv run pytest` 538 passed; `bash scripts/check_all.sh` green; Flight Deck unit tests (153) and
  end-to-end tests (17) green.

## In flight
- The pull request for `step-6c/sweep-held-point` awaits the human's merge; it is watched.
- #152 (blocker): the capture end-to-end test sometimes times out on CI waiting for "replaying" after the
  overlays click. The diagnostic from #156 is on `main`, so the next failure's message says whether the
  replay route was slow or the message was overwritten. Fix it from that message, with `Fixes #152`.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #150, #130, #122, #120, #119.

## Known broken
- #152, above: a flaky end-to-end test that can red any pull request's `flightdeck` job. Everything else:
  `gh issue list`.

## Next action
**Agent, next session:** if a `flightdeck` job has failed with the #152 diagnostic, fix #152 first. Otherwise
go back to Step 6c: deliverable 11 (#76), then 14 (#112), then 15 (#114), on a branch `step-6c/<short-name>`.
**Human:**
- Merge this pull request (#157 and #158).
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
- **2026-10-29 (session 36, continued):** "Yes the sweep should open with where the voltages are currently
  sitting. And yes make a script to regenerate the guide screenshots" → #157, #158.
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
