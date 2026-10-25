# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS. Goal 1:
deliverables 2 (code half), 3, 4 in L0 (PR #121); **deliverable 1 rehearsed end to end** on the human's
personal PC and Mac (runbook Parts 1–10, 2026-10-23/24, `bench/reports/2026-10-24-step6c.md`, PR #131);
**deliverable 5 (the command token) built this session** on `step-6c/command-token`, ADR 0082. Steps 0–6
and 6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/command-token` (PR against `main`; the human merges). Merged today: #127, #131;
#134 (drill date, records decision) may still be open.
**Last session:** 2026-10-24 (session 29, second half: deliverable 5), no bench.

## Done this session
- **Deliverable 5, the command token (ADR 0074 → ADR 0082).** `qdt_server/auth.py`: a token file
  (`Settings.tokens`, default `<root>/tokens`; one token per line, a label after it, `#` comments; read on
  every command, so deleting a line revokes; missing = every command from elsewhere refused, logged at
  start), `is_loopback` (127/8, `::1`, IPv4-mapped; a non-IP peer counts as another computer), and
  `command_token(path)`, a dependency on the `stand` router that challenges any method but
  GET/HEAD/OPTIONS from a non-loopback peer: 401 + `WWW-Authenticate: Bearer` without a token or with
  one not in the file. Reads, `POST /stream/replay` and the CORS preflight are never challenged; the CORS
  middleware stays outside so the 401 reaches the browser. `python -m qdt_server --tokens <file>` and
  `--add-token "<label>"` (prints a `token_urlsafe(32)` once, chmod 600 where modes exist). Flight Deck:
  `ApiClient(base, fetch, token)` sends `Authorization: Bearer` on every call when it has one;
  `commandToken()` takes `?token=`/`#token=`, keeps it in `localStorage` per API base, `main.ts` drops it
  from the address with `replaceState`. Tests: `packages/qdt-server/tests/test_tokens.py` (refusal,
  acceptance, revocation, loopback exemption incl. `::1`, missing file, replay open, preflight + CORS on
  the 401, file format, default path) and three cases in `apps/flightdeck/test/control.test.ts`.
  `TestClient`s in `test_api.py`, `conftest.py` and tutorial 04 now speak from `("127.0.0.1", 50000)`;
  the default peer `testclient` is not an address. OpenAPI export unchanged (`check:api` OK).
  `packages/qdt-server/CLAUDE.md` rule rewritten ("no authentication in Step 4b" is gone).
- pytest 491 passed, 4 skipped (was 476); Flight Deck 145 unit tests; `check_all` green except the
  pre-existing #125 (vocabulary; `ruff format --check` also lists 28 pre-existing files, none touched);
  `uv lock --check` clean. Flight Deck e2e 13/15: the two failures in `workspace.test.ts` are pre-existing
  and local (this PC runs the demo's read server on :8700, which the test's default `?api=` finds; #135).
- Earlier today (first half, PR #131 + #134): the runbook's Parts 8–10 fixed as the human ran them, the
  demo declared complete, restore drill #2 set for 2026-10-31 (#133), the ~80 pre-deployment records
  kept for the human's review. Filed #132 (Dependabot: `certifi`).

## In flight
- PR for `step-6c/command-token` awaits the human's merge; #134 too if not yet merged.
- **Still unverified:** `deploy/qdt-db/mac-payload-mount.sh` as a script (merged in #126; the steps it
  automates are verified by hand). The human runs `uninstall` then `install` on the Mac as the test.
- The token is not yet in the runbook: ADR 0082's "must now" puts a token section where a stand server
  is first bound off loopback (the lab PC, deliverable 13). The demo laptop runs Flight Deck and the
  stand server together, so it needs none.
- Open UI findings: #130, #122, #120, #119.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** the scripted `bench/test_l1_remote_read.py` for R-1 … R-4 (`PLANNED_BY` the step
file), so the lab-PC run of the runbook is a pytest bench report rather than a hand-written one; R-4 is
now testable (a command from another computer without a token is refused). Then deliverable 6 (the plan
§9 IT checklist rewritten from Analysis 0003 and this step). Branch `step-6c/<short-name>`. Blockers from
the human's machines first, if any appear.
**Human:** merge the PR(s); the Mac mount script's `uninstall`/`install` test; review the ~80
pre-deployment records for gaps in what a measurement record carries (findings → issues on
`Deployment`); restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
- **2026-10-24 (session 29):** ran Parts 6–10 of the runbook. "For the purpose of this demonstration, I
  don't have a third workstation or NAS to serve as backup, so then the host will have to be the database
  PC (`qdt-db`) but on a different drive." On the missing-dash fault: "there's no need to add that to the
  appendix." "The demo database deployment has been completed. Everything works as expected." "Schedule
  the next drill for next week" (2026-10-31, #133). "Keep the predeployment records for me to review for
  gaps in information in measurement records." Then: "start deliverable 5."
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
