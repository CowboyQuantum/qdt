# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS. Goal 1:
deliverables 2 (code half), 3, 4, 5, 6 and 12 done, deliverable 1 rehearsed on the human's personal PC and
Mac (`bench/reports/2026-10-24-step6c.md`), the L1 rows scripted (`bench/test_l1_remote_read.py`). Goal 2:
**deliverable 7 in L0 this session (ADR 0085).** Steps 0–6 and 6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/stand-state`, restarted from `main` after #143 (Analysis 0007) and #144 (deliverable
7) were merged on 2026-10-27; it now carries only the watcher rule (root `CLAUDE.md`, End step 6).
**Last session:** 2026-10-27 (session 31), no bench.

## Done this session
- **Schema** (`packages/qdt-schemas/src/qdt_schemas/operations.py`): `ChannelLimit` (a closed range of
  finite numbers in the channel's SI unit) and `StandState` (stand, version, limits, couplings, the held
  point as `FixedLevel`s, who, when, why), persisted, with a version 1 fixture and the JSON Schema export.
- **Compiler** (`qdt_lab.experiment`): `driven_extents` and `check_limits`; `compile_sweep(...,
  stand_state=)` raises `LimitError` (a `ValueError`) naming every channel beyond its limit. Counted: the
  operating point, every stepped axis, every coupled companion, and every pulse step, ramp and drive.
- **Registry**: the `stand_states` table (DDL 4, additive; versions consecutive per cache; synced last);
  `add_stand_state`, `stand_state`, `stand_states`, `pull_stand_states`. A role that may not add tables
  meeting a version 3 server is told to run `python -m qdt_registry init` as the admin.
- **Server** (`packages/qdt-server/src/qdt_server/state.py`, `runs.py`, `app.py`, `auth.py`): version 1 at a
  stand's first start; a version for every level set or release, every limits or couplings change
  (`POST /stand/state`, with a reason) and every discarded offer, `set_by` from the token's label or
  `local`; refusal at click-to-set, compile, submission and when a queued run starts; after a restart the
  held point is offered (`GET /levels/pending`) and applied only by `POST /levels/pending/confirm`
  (`DELETE` discards); history on both servers at `GET /stand-states`; a new cache pulls the stand's
  versions from the registry server at start (10 s at most). OpenAPI and Flight Deck's generated types
  regenerated. Runbook: the schema step is re-run after a layout bump.
- pytest 520 passed, 4 skipped (was 495); registry tests also green on a local Postgres 16 before the last
  small change (the clearer error message); `check_all` green; Flight Deck typecheck and 145 unit tests
  green; e2e not run here (#135).

## In flight
- The pull request for the watcher rule awaits the human's merge; it is watched (End step 6).
- **The Phantom cutover, queued, not started** (Analysis 0007; qdt #140, #141, #142; Phantom #40, #41).
  Before any qdt code it needs a step file (ADR 0071), with #141 as its first deliverable.
- Flight Deck still keeps its own limit and coupling matrix in the browser; the server's limits hold
  regardless. The widgets move to `/stand/state` and `/levels/pending` in deliverable 8 (ADR 0085 §7).
- The token is not yet in the runbook: ADR 0082 puts it where a stand server is first bound off loopback
  (the lab PC, deliverable 13).
- Open UI findings: #130, #122, #120, #119. Pre-existing local e2e failures in `workspace.test.ts`: #135.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** **deliverable 8** (ADR 0075, 0084, 0085; #78, #79): `QueuedRun` in
`qdt_schemas.operations` with `RunRequest` moved from `qdt_server.app` into `qdt-schemas` (one commit with
every consumer); the run queue in the stand server, persisted in its cache, ordered, one run at a time,
reorder and remove while queued, abort while running; Flight Deck's queue, Levels and Virtual gates widgets
on the server's routes, with a prompt to confirm or discard an offered held point; the L0 rows "Queue" and
"Flight Deck e2e" in the step file. Closes #78 and #79. Branch `step-6c/<short-name>`. Blockers from the
human's machines first, if any appear.
**Human:** merge the watcher-rule pull request. On the rehearsal `qdt-db`, update the repository and run
`uv run python -m qdt_registry init` with the admin role (runbook Part 4): the layout is now version 4,
and until then the laptop's sync and the read server stop with a message saying so. Still open from before:
send plan §9 to IT; `ipconfig` on the measurement PC for #80; the rest of ADR 0077 before deliverables
9–10; the runbook on the lab PC, then `bench/test_l1_remote_read.py` from a desk; review the
pre-deployment records; restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
- **2026-10-27 (session 31):** asked for notes on making qdt compatible with Phantom (they are Analysis
  0007, PR #143, and issues #140–#142), then: "Ok then continue with deliverable 7." After #144 was
  opened: "Yes, make sure all agent submitted PRs have a watcher armed going forward" → root `CLAUDE.md`,
  End step 6, and `.claude/commands/session-end.md` step 6.
- **2026-10-27 (session 30, detour):** asked for the Phantom cutover to be laid out; answered Analysis
  0007's questions: "move the sequencer interpreter into qdt lab as you say. device file makes more sense.
  Let's hold off on deciding the release cadence. I don't see a decision needed for the simulated stand."
- **2026-10-25 (session 30):** "accept 0075" (ADR 0084); discovery starts with instruments connected
  directly to the computer, with an address range "for future specification when I understand how we can
  isolate the rack ips to a vlan or range"; the writing guidance lives in root `CLAUDE.md`.
- Earlier direction, verbatim: `git show d7c7a01:docs/STATUS.md`, § Direction recorded (sessions 26–30),
  and `git show b94193f:docs/STATUS.md` (sessions ≤ 25).

## Decisions pending
All are `decision` issues (`gh issue list --label decision`), plus Step 6c's remaining open decision:
ADR 0077 (before deliverables 9–10; its discovery scope is already narrowed by ADR 0084, #80). Settled:
ADR 0075 (ADR 0084) and its details (ADR 0085). Held by the human (2026-10-27): Phantom's release cadence
against qdt's pin (Analysis 0007, answer 3).
