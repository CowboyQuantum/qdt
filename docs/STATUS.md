# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** is DONE (pull request #151 merged,
ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6c/read-server-start-docs` (pull request against `main`; the human merges).
**Last session:** 2026-10-29 (session 37), on the rehearsal `qdt-db`, no bench.

## Done this session
- **The read server on the rehearsal `qdt-db` was restarted** at the human's request, through its scheduled task
  (`Stop-ScheduledTask`, then `Start-ScheduledTask`, from an ordinary PowerShell window). The old process
  released both ports; the new one answered `/server` and `/records` after about ten seconds.
- **Runbook (Step 6c deliverable 1), the human's request: how to start the read server.** Part 6 of
  `deploy/qdt-db/README.md` gains *Starting, stopping and restarting it later*:
  - It says when to start or restart by hand: after a repository update (in the order update, `init` if the
    table-layout version rose, rebuild the page, restart), after editing `read-server.ps1`, when the task has
    stopped, and when the server stops answering.
  - It gives the scheduled-task commands and the Task Scheduler clicks.
  - Its check covers `/server`, `/records` and the two listening ports. It says that the result 267009
    (0x41301) means "running", not an error.
  - It says the task shows no window, so errors are read by running the script by hand.
  - Cross-links: Part 6 step 1 (restart after a rebuild), Appendix B's port-conflict row, and the
    `Internal Server Error` row, which now names the table-version cause as well as the password.
  - *Where things live* now says the repository on `qdt-db` should be a clone only the read server uses.
- **Diagnosed: scans no longer reached the read server.** The registry server was still at `ddl_version` 3,
  while `main` has been at 4 since 2026-10-27 (ADR 0085). A stand server on `main`'s code meets the old tables,
  tries `CREATE TABLE stand_states` as `qdt_writer`, and is refused. PostgreSQL's log on `qdt-db` shows
  `permission denied for schema public` for that statement at 14:45:59 (twice) and 14:46:35 today. The read
  server faithfully listed the 93 records the database held, the newest from 2026-10-25. Nothing is lost: the
  refused records wait in the stand server's cache until a sync succeeds. The fix is the human's standing
  item, `qdt_registry init` as `qdt_admin`; the human was given a block that prompts for the password.
- Checks: `uv run pytest` 538 passed, 4 skipped; `bash scripts/check_all.sh` green except
  `check_vocabulary`, which fails only on Windows (#125, the backslash paths). The local environment needed
  `uv sync --all-packages --all-extras` to install Phantom before the suite would collect.

## In flight
- The pull request for `step-6c/read-server-start-docs` awaits the human's merge; it is watched.
- #152 (blocker): the capture end-to-end test sometimes times out on CI waiting for "replaying" after the
  overlays click. The diagnostic from #156 is on `main`, so the next failure's message says whether the
  replay route was slow or the message was overwritten. Fix it from that message, with `Fixes #152`.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #150, #130, #122, #120, #119.

## Known broken
- #152, above: a flaky end-to-end test that can red any pull request's `flightdeck` job.
- On the rehearsal `qdt-db`, until `qdt_registry init` has run as the admin: no stand server on `main` can sync,
  and a read server restarted on `main`'s code answers `/records` with `Internal Server Error`. The read server
  started today runs the code checked out before this session's branch switch and still answers.
- Everything else: `gh issue list`.

## Next action
**Agent, next session:** if a `flightdeck` job has failed with the #152 diagnostic, fix #152 first. Otherwise
go back to Step 6c: deliverable 11 (#76), then 14 (#112), then 15 (#114), on a branch `step-6c/<short-name>`.
**Human:**
- Merge this pull request.
- On `qdt-db`, run `uv run python -m qdt_registry init` as `qdt_admin`. It should print `server ready,
  ddl_version 4`. Then restart the read server through its task (the new runbook section), and run one scan
  or restart the stand server: its next sync uploads every record that waited.
- Decide #150 (click-to-set on a pulsed axis) and #147 (the two L2 oracles).
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
- **2026-10-29 (session 37):** "can you help me restart the remote server on this database computer?", then
  "make sure there is documentation on how to start the read server.", then "ok but for some reason when I
  run a scan on qdt server I am no longer seeing it on the read server, even when I refresh the widget and
  the whole page" → the restart, the runbook section, the `ddl_version` diagnosis.
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
- Earlier direction, verbatim: `git show 812d631:docs/STATUS.md` (sessions 30–31), `git show f748fe2:docs/STATUS.md`
  and `git show d7c7a01:docs/STATUS.md`, § Direction recorded, and `git show b94193f:docs/STATUS.md`
  (sessions ≤ 25).

## Decisions pending
- All `decision` issues (`gh issue list --label decision`), now including #150 (click-to-set on a pulsed
  axis) and #147 (the two L2 oracles).
- Step 6c's ADR 0077, needed before deliverables 9 and 10 (#80).
- Held by the human: the cadence of Phantom releases against qdt's pin (Analysis 0007, answer 3). Each pin
  bump is its own pull request (ADR 0087).
