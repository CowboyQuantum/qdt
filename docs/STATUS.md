# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: goal 1's first
slice is in L0 (deliverables 2 code half, 3, 4; PR #121 merged), and **the `qdt-db` runbook (deliverable 1)
has now run end to end, Parts 1–10, on the human's personal PC and Mac laptop**: "the demo database
deployment has been completed. Everything works as expected" (2026-10-24). Steps 0–6 and 6b are DONE.
Milestone `Deployment`.
**Branch:** `step-6c/runbook-paths` (PR #131 against `main`; the human merges). Merged today: #127 (paths
are the reader's choice; `--root`; `read-server.ps1` by name). Earlier: #126, #124, #123.
**Last session:** 2026-10-24 (session 29: the human ran Parts 8–10 with the agent fixing the runbook as
problems appeared), no pytest bench run; a hand-written report `bench/reports/2026-10-24-step6c.md`.

## Done this session
- **Runbook Parts 6–10 ran on the real machines** (personal Windows PC = `qdt-db`, PostgreSQL 18; Mac laptop
  over Tailscale, simulated stand), following Parts 1–5 from session 28. Part 8's smoke test passed in all
  three forms (sweep on the laptop → record in the PC's Flight Deck and in a script; with the laptop off;
  after a reboot with nobody logged in). Part 9's nightly backup runs as a scheduled task and the restore
  drill was done (2026-10-24, the human's `drill-date` line in the report). Part 10's checklist ticked.
  R-1 … R-3 of the step file are therefore passed by hand; see the bench report for the mapping.
- **Runbook fixes from the run** (all in PR #131, docs only):
  - Part 8 step 3 (morning): the addresses depend on whether the computer knows the name `qdt-db`; on
    `qdt-db` itself use `127.0.0.1`; run the script inside the repo.
  - Part 9 step 1: the human looked for a folder named `%APPDATA%`. The step now gives the full
    `pgpass.conf` path, creates the folder from PowerShell with `$env:APPDATA`, and checks that `psql`
    connects as the admin without a prompt.
  - Part 9 step 2: the human has no third machine or NAS, only a second disk in the PC. The script now takes
    one `$dest` (a second **physical** disk in `qdt-db`, told from a partition in Disk Management, or a share
    elsewhere) and writes `dumps\`, `payloads\` and `payloads.log` under it, so the dumps also leave `C:`.
    The paths table follows. What a second disk does and does not protect against is stated.
  - Part 9 step 2–3: run `backup.ps1` by hand with the task's exact command before scheduling it; the
    script keeps a transcript in `C:\qdt\backup.log` so a scheduled run leaves evidence. The actual fault was
    the task's action typed without the dash before `-ExecutionPolicy`; the human asked that this **not**
    go into Appendix B, and the row was reverted.
- **Filed:** #132 (Dependabot: `certifi` in `uv.lock`, critical, patched in 2026.10.19; `backlog`, not a
  blocker). The bench report file was created by the human (the drill date) and completed by the agent.
- No code changed. `check_all` green except the pre-existing #125 (vocabulary); pytest 476 passed, 4 skipped.

## In flight
- PR #131 awaits the human's merge (five docs commits plus this STATUS/report/step-file commit).
- **Still unverified:** `deploy/qdt-db/mac-payload-mount.sh` as a script (merged in #126; the steps it
  automates are verified by hand). The human runs `uninstall` then `install` on the Mac as the test.
- The database holds ~80 records dated before it existed, from a development cache synced at a stand
  server's first start (ADR 0080); the human has not said whether to keep them or give the lab stand its
  own `--root`.
- Open UI findings from the run: #130 (History's open/analyse buttons hidden when the pane is narrow),
  #122, #120, #119.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** deliverable 5 (the command token: a stand server bound off loopback refuses
`POST`/`DELETE` without a bearer token from its token file; loopback exempt; Flight Deck sends the token it
was given and hides commands on a read-only server) with the step file's L0 rows, then the scripted
`bench/test_l1_remote_read.py` for R-1 … R-4 so the next runbook run (the lab PC) is a pytest run, not a
hand report. Branch `step-6c/<short-name>`. Blockers from the human's machines first, if any appear.
**Human:** merge #131; decide on the ~80 pre-deployment records; put the next restore drill in the
calendar; the lab PC is a second run of the same runbook when its time comes (deliverable 1's last part;
deliverable 6, the IT checklist, precedes it).

## Direction recorded (human)
- **2026-10-24 (session 29):** ran Parts 6–10. "For the purpose of this demonstration, I don't have a third
  workstation or NAS to serve as backup, so then the host will have to be the database PC (`qdt-db`) but on
  a different drive." On the missing-dash fault: "there's no need to add that to the appendix." Then: "the
  demo database deployment has been completed. Everything works as expected."
- **2026-10-23 (session 28):** ran the runbook on the personal PC and the Mac; asked for the runbook to be
  updated with the Mac mount method "at least for macbooks"; asked whether Windows needs the same (no: the
  UNC path connects on demand with `cmdkey`'s credential and fails safely when the share is away) and
  whether the mount point can be made unmovable (`chflags uchg`; confirmed the mount still works). Then: "Is
  there any way to create a script to generate this folder and all of these things we did today … so that
  a user doesn't screw it up? … we can just create a separate script for [Windows] when we debug in the
  future" (Windows needs no mount; a `check` script is the likely shape if one is ever needed).
- **2026-10-22 (session 27):** the next focus is "set up the measurement database backend on my desktop PC
  and have it running … launch Flight Deck from my laptop with a simulated backend … take a measurement …
  view that measurement on my desktop computer by querying the database … with both an instance of Flight
  Deck on my desktop and through a Python script" (Step 6c goal 1, deliverables 1–4). "I think I want to
  accept ADR 0074" (ADR 0080). "For this demo, the database PC is not the real lab database PC. I want to
  demo this on my personal PC before trying to clone this repo on the lab PC." "I don't want to do manual
  sync — please add a sync attempt after every measurement, and if the database PC is not reachable
  default to the local cache." "Both my personal PC and the lab PC are Windows, for now. We can keep the
  desire to have the lab be a Linux box with documented reasons, but for now it's Windows."
- **2026-10-22 (chat instance, via PR #117):** ADRs 0078 (boundaries) and 0079 (general electronic test)
  proposed; Analyses 0005–0006 with the human's answers.
- **2026-10-19 (session 26):** ADR 0071, 0072, 0073 and the four deployment goals; the verbatim record is in
  `git show 5f2dd72:docs/STATUS.md`, § Direction recorded.
- Earlier direction (sessions ≤ 25): `git show b94193f:docs/STATUS.md`, § Direction recorded.

## Decisions pending
All are `decision` issues (`gh issue list --label decision`), plus Step 6c's remaining open decisions:
ADR 0075 (before deliverables 7–8), ADR 0077 (before 9–10), the LAN probe range (with deliverable 6).
How a script gets payload bytes is settled: HTTP from the read server (ADR 0081).
