# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS. Goal 1:
deliverables 2 (code half), 3, 4, 5 in L0; **deliverable 1 rehearsed end to end** on the human's personal
PC and Mac (runbook Parts 1–10, 2026-10-23/24, `bench/reports/2026-10-24-step6c.md`); **this session: the
L1 rows scripted (`bench/test_l1_remote_read.py`), deliverable 6 (plan §9) written, deliverable 12 (#77)
done, ADR 0075 accepted (ADR 0084).** Steps 0–6 and 6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/l1-remote-read` (PR against `main`; the human merges). Merged before this session:
#134, #136 (the command token).
**Last session:** 2026-10-25 (session 30), no bench.

## Done this session
- **`bench/test_l1_remote_read.py`** (`PLANNED_BY` the step file): the runbook's Part 8 as a pytest run.
  R-1: the record listed by the read server, its payload over HTTP with a matching `X-Content-SHA256`,
  read by a script through `qdt_registry` as the reader, whose `sync` of a probe device is refused by the
  server. R-2: skips unless `QDT_L1_REMOTE_CONDITION=stand-off`, then fails if the stand server still
  answers, then R-1. R-3: `rebooted`, the operator's declaration (a test cannot reboot `qdt-db`), then
  R-1. R-4: every stand-router command (`POST`/`DELETE /levels`, compile, `POST /runs`, abort) with no
  body, without a token and with a wrong one → 401 + `WWW-Authenticate: Bearer`; the held levels, the run
  list and (with `QDT_SCOPE_ADDRESS`) the scope's DC reading unchanged; skips when the stand address is
  this computer. Variables: `QDT_READ_SERVER_ADDRESS`, `QDT_READER_DSN`, `QDT_STAND_SERVER_ADDRESS`,
  `QDT_L1_RECORD_ID` (default newest). Checked end to end on this PC: a stand server on `0.0.0.0` and a
  read server on a SQLite registry, the stand addressed by this PC's network address — R-1 and R-4 pass,
  `rebooted` passes R-3, `stand-off` with the stand still up fails as designed. Runbook Part 8 step 6
  documents the three runs.
- **ADR 0083 (#77, deliverable 12):** `scripts/bench_report.py` files a run under the step its tests'
  `PLANNED_BY` resolves to (step file, else the highest-numbered ADR's `**Step:**` line), one section per
  step per run; `bench_step` removed from `pyproject.toml` (fallback `unplanned`); `QDT_*_DSN` values and
  URLs with credentials redacted. Every existing bench test resolves (loopback/capture/current → 5,
  paced/sensor/two-lines/segments/opx_streaming → 6, remote_read → 6c). Four new tests in
  `packages/qdt-lab/tests/test_bench_report.py`.
- **Deliverable 6:** plan §9 rewritten as the IT checklist to send (ten asks: the PC, name/address, 5432
  + 445 + 8700/8765 from the lab subnet, 8700/8765 from the office subnet, 8700/8765 on the measurement PC
  for a second desk with the token, Update policy, off-machine backup place, service account, instrument
  network + the opt-in probe question, TLS off-subnet; Docker and 8100/9000/9001 retired). The human sends it.
- pytest 495 passed, 4 skipped (was 491); `check_all` green except the pre-existing #125 (vocabulary) and,
  locally only, `provenance_check` matching a byte pattern inside the gitignored `.ruff_cache` (CI has no
  cache; tracked files are clean). `check_bench_rows` needs `PYTHONUTF8=1` on Windows (cp1252 default).

## In flight
- PR for `step-6c/l1-remote-read` awaits the human's merge.
- The token is not yet in the runbook: ADR 0082's "must now" puts a token section where a stand server
  is first bound off loopback (the lab PC, deliverable 13).
- Open UI findings: #130, #122, #120, #119. Pre-existing local e2e failures in `workspace.test.ts`: #135.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** **deliverable 7** (ADR 0075, accepted by ADR 0084): the `operations.py` slice —
`ChannelLimit`, `StandState` (per-channel limits, the coupling matrix, the held operating point; versioned,
append-only, who/when/why) and `QueuedRun`, every field with `description=`; `StandState` versions as
registry records (a new table set: `DDL_VERSION` bump, DDL export, additive migration, ADR per
`packages/qdt-registry/CLAUDE.md`); the stand server loads the latest version at start, refuses (never
clamps) a level or a compiled sweep beyond a limit, and re-applies the held point after a restart only on
confirmation; routes on the stand router (commands need the token); L0 rows "`StandState`" in the step
file. Then deliverable 8 (the queue in the stand server; #78) and Flight Deck's Levels, Virtual gates and
queue widgets switched to the server. Branch `step-6c/<short-name>`. Blockers from the human's machines
first, if any appear.
**Human:** merge PR #138; send plan §9 to IT (fill the placeholders; row 9 is informational for now); on the
measurement PC, `ipconfig` tells whether the rack-facing interface has its own address range (#80), which
decides how the probe range is specified later; decide the rest of ADR 0077 (inventory vs binding, binding
by identity, drivers declare ports, the pool, the widget) when deliverables 9–10 come up; when the lab PC
exists, run the runbook there and then `bench/test_l1_remote_read.py` from a desk (Part 8 step 6); review
the ~80 pre-deployment records for gaps (findings → issues on `Deployment`); restore drill #2 on 2026-10-31
(#133).

## Direction recorded (human)
- **2026-10-25 (session 30):** "the mac mount script was confirmed by me last night" (the `uninstall`/
  `install` test of `deploy/qdt-db/mac-payload-mount.sh`, 2026-10-24). "Otherwise continue." On ADR 0075:
  "I think it makes sense for the voltage limits and the voltage state of the instruments to belong to the
  stand and NOT have that belong to the front end" (matches the ADR; not yet an acceptance — the queue half
  and the refuse-never-clamp and confirm-before-reapply details were explained, awaiting "accept 0075").
  On ADR 0077: the instruments relevant to discovery hang off a rack switch with an optical uplink to the
  lab network, and "the measurement pc is hardwired to the rack switch"; discovery should search only that
  switch and instruments connected directly to the measurement PC. Agent's reading recorded on #80:
  discovery per network interface, probe range derived from the interface and capped, mDNS on that
  interface only, VISA enumeration for direct connections; one check pending — whether the rack-facing
  interface is on its own address range (fenced) or on the lab subnet through an untagged uplink (not
  fenced). Then: **"accept 0075. for now with the instrument discovery, let's just design so that we can
  discover anything connected to the computer directly and then allow an ip range for future specification
  when I understand how we can isolate the rack ips to a vlan or range"** → ADR 0084. Also asked that the
  writing guidance (complete sentences, acronyms expanded, no comma-separated triplets) live in the repo:
  root `CLAUDE.md`, "Writing for the human".
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
All are `decision` issues (`gh issue list --label decision`), plus Step 6c's remaining open decision:
ADR 0077 (before deliverables 9–10; its discovery scope is already narrowed by ADR 0084 — direct
connections now, a configured probe range later once the rack's isolation is known, #80). Settled: ADR
0075 (ADR 0084, 2026-10-25); how a script gets payload bytes — HTTP from the read server (ADR 0081).
