# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS. Goal 1:
deliverables 2 (code half), 3, 4, 5, 6 and 12 done; deliverable 1 rehearsed (`bench/reports/2026-10-24-step6c.md`);
the L1 rows scripted. Goal 2: deliverables 7 and 8 in L0 (ADR 0085, 0086; PRs #144, #146); **the L2 rows
scripted this session** (`bench/test_l2_orchestration.py`). Steps 0–6 and 6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/l2-orchestration` (PR against `main`; the human merges).
**Last session:** 2026-10-28 (session 33), no bench.

## Done this session
- **`bench/test_l2_orchestration.py`** (`PLANNED_BY` the step file): T-1 … T-7, each a queue entry to a
  `qdt-server --stand` the file runs itself from `QDT_STAND_FILE` (so T-1 restarts it and confirms the offered
  held point); the scope read through records fetched over HTTP; `QDT_L2_ROWS` names the rows cabled now
  (default T1–T4, T7; T-5 needs the board on ch1, T-6 the two OPX lines on ch1 and ch3). `QDT_L2_SIMULATED=1`
  runs it against the simulated stand: T-1, T-2 and T-7 pass; T-3 … T-5 run and skip only their bench oracles;
  T-6 skips. That run's report was deleted, since it proves no hardware.
- **#147** (found-by-agent, decision): T-7's "scope reads the held point afterwards" cannot pass (a sweep
  leaves its last level, the held point is not re-applied), so the row checks the scope against P1's reported
  setpoint; T-5 runs L2-1's DC half only (its pulse half needs the OPX outside the stand).
- **Phantom checked** (read-only clone, `/home/user/cowboyquantum/phantom`): its Step 8 side is merged with qdt's
  six requests built (`phantom.api`, `Session`, `Device.truth`/`knowable`, `python -m phantom.contract`), version
  0.2.0 in `pyproject.toml`, but **no tag exists**: its session's tag push got HTTP 403, and ADR 0025 there says
  the owner tags (or tells a session to).
- pytest unchanged (no package code touched); `check_all` green; the bench file skips cleanly when unconfigured.

## In flight
- The PR for `step-6c/l2-orchestration` awaits the human's merge; it is watched.
- **The Phantom cutover (#140, #141, #142), queued since 2026-10-27, not started.** What stops it: (1) it has no
  home in the plan: ADR 0071 needs a step file (and an ADR placing it against Step 6c, as ADR 0073 placed 6c),
  which no session wrote because every STATUS since named Step 6c's next deliverable; (2) #140 and #142 pin a
  Phantom *tag* (Analysis 0007, plan §10), and `v0.2.0` is not tagged. #141 needs neither the tag nor Phantom.
- The token is not yet in the runbook (deliverable 13, the lab PC).
- Open UI findings: #130, #122, #120, #119.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Human first:** say whether the cutover goes now or after Step 6c. **Agent, next session:** if now, write the
cutover's step file (`docs/steps/06d-phantom-cutover.md`: #141 first, then #140 + #142 in one PR against the
tag) and its ADR (placing it; Phantom pinned by git tag, imported only by `qdt-sim`; amends ADR 0078's physics
row, supersedes ADR 0020's model), then #141 (the interpreter into `qdt_lab.simulated`, outputs bit-identical).
If after, deliverable 11 (#76), 14 (#112) and 15 (#114). Branch `step-6c/<short-name>` or the cutover's.
**Human:** merge this PR; tag Phantom `v0.2.0` (its STATUS names `f72daac`; `main` is now `84f9efa`, with #45's
docs on top) or say to pin a commit instead; decide #147; on `qdt-db`, `uv run python -m qdt_registry init` as
the admin; run `bench/test_l2_orchestration.py` on the bench with `QDT_STAND_FILE`; still open: plan §9 to IT,
`ipconfig` for #80, ADR 0077 before deliverables 9–10, the runbook on the lab PC, the pre-deployment records,
restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
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
All are `decision` issues (`gh issue list --label decision`), now including #147 (two L2 oracles), plus Step
6c's ADR 0077 (before deliverables 9–10, #80). New: when the Phantom cutover runs, and whether qdt pins a tag
or a commit. Held by the human: Phantom's release cadence (Analysis 0007, answer 3).
