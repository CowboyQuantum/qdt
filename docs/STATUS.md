# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: goal 1's first
slice is in L0 (deliverables 2 code half, 3, 4; PR #121 merged); the `qdt-db` runbook (deliverable 1) is
being run for the first time on the human's personal Windows PC and Mac laptop — Parts 1–5 done, Part 6
onward not yet. Steps 0–6 and 6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/runbook-mac-mount` (PR against `main`; the human merges). Earlier: #123 (runbook
rewritten for a reader new to PostgreSQL) and #124 (Windows and Mac versions of every laptop-side step).
**Last session:** 2026-10-23 (session 28: the human's first run of the runbook, with the agent fixing the
runbook as problems appeared), no bench.

## Done this session
- **Runbook Parts 1–5 ran on real machines** (personal PC = `qdt-db`, PostgreSQL 18; Mac laptop over
  Tailscale). Postgres service, roles, `init` (`ddl_version 3`), the SMB share and the Mac's Cmd-K mount all
  worked as written. What did not, and what the runbook now says instead:
  - **Mac share at login (Part 5, step 5).** A network volume in System Settings' *Login Items* does nothing
    at login on current macOS, and the two Finder-based alternatives tried (`osascript 'mount volume'`,
    `open smb://…`) either fail with error -5014 at login or stop at a pre-filled password dialog. The
    runbook now installs a Launch Agent (`~/Library/LaunchAgents/com.qdt.mount-payloads.plist`) running a
    script that mounts with `mount_smbfs` onto `~/qdt-payloads`, reading the password from the keychain
    entry Finder saved (`security find-internet-password -w`; *Always Allow* once), retrying for five minutes
    while the network comes up, logging to `~/Library/Logs/mount-qdt-payloads.log`. The mount point is
    `chmod 555` so an unmounted share refuses writes instead of swallowing payloads locally (the fail-safe
    `/Volumes` gave for free). Verified on the human's Mac through a log-out/log-in, chmod included. Part 7's Mac path,
    the Part 10 checklist and Appendix B follow.
  - **Tailscale on the Mac** had stopped starting at login (its Login Items entry was lost while editing the
    list); the runbook now says to check it, and why.
  - **Appendix B:** `Can't load plugin: sqlalchemy.dialects:postgreswl.psycopg` = a typo in the DSN prefix.
  - **PostgreSQL 18** is what the installer now gives; the service-name mentions say 17 or 18.
- No code changed. `check_all` green; pytest run at session end (see the PR).

## In flight
- This PR awaits the human. The `chmod 555` mount point is verified on the human's Mac (write refused when
  unmounted, mount still works). **Unverified:** whether `chflags uchg` (Finder's *Locked*) on the mount
  point still allows the mount — if yes, one line to add.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Human (the demo, deliverable 1 and 2's share):** continue `deploy/qdt-db/README.md` from Part 6 (the read
server as a start-up task) through Part 7 (the Mac's two variables; `QDT_PAYLOAD_STORE` is now
`$HOME/qdt-payloads`) and the Part 8 smoke test: a sweep on the laptop's Flight Deck, the record in the
desktop's Flight Deck (no Run button) and in a script (tutorial 04's pattern). Every step that needs a
workaround becomes an issue on `Deployment` or a runbook fix in-session, as today. Tick Part 10's
checklist. **Agent, next session:** blockers from the demo first; otherwise deliverable 5 (the command
token: a stand server bound off loopback refuses `POST`/`DELETE` without a bearer token from its token
file; loopback exempt; Flight Deck sends the token it was given), with the step file's L0 rows.
Branch `step-6c/<short-name>`.

## Direction recorded (human)
- **2026-10-23 (session 28):** ran the runbook on the personal PC and the Mac; asked for the runbook to be
  updated with the Mac mount method "at least for macbooks"; asked whether Windows needs the same (no: the
  UNC path connects on demand with `cmdkey`'s credential and fails safely when the share is away) and
  whether the mount point can be made unmovable (`chflags uchg`, pending a test that the mount still works).
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
