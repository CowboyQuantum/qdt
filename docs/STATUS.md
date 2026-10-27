# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS. Goal 1:
deliverables 2 (code half), 3, 4, 5, 6 and 12 done; deliverable 1 rehearsed on the human's personal PC and
Mac (`bench/reports/2026-10-24-step6c.md`); the L1 rows scripted (`bench/test_l1_remote_read.py`). Goal 2:
deliverable 7 in L0 (ADR 0085, PR #144) and **deliverable 8 in L0 this session (ADR 0086).** Steps 0–6 and
6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/run-queue` (PR against `main`; the human merges).
**Last session:** 2026-10-27 (session 32), no bench.

## Done this session
- **Schema:** `QueuedRun` (ADR 0075's fields plus `record_id`, `started_at`, `finished_at`, `message`) and
  `StandQueue` in `qdt_schemas.operations`; `RunRequest` moved from `qdt_server.app` to
  `qdt_schemas.control`; `QueuedRun` persisted with a version 1 fixture.
- **Registry:** a second cache-local mutable table, `run_queue` (`queue_put`, `queue_entries`,
  `queue_drop`), never synced, no change to the shared layout (still DDL 4).
- **Server** (`packages/qdt-server/src/qdt_server/run_queue.py`): a worker runs one entry at a time through
  `RunManager.start`, so limits are checked again at start; `GET`/`POST /queue`, move, remove, abort,
  pause, resume, all on the token-guarded stand router; after a restart with entries waiting the queue is
  paused with a note, and an entry running at the stop is recorded as aborted. `RunManager.wait` added.
- **Flight Deck:** a Queue widget (default layout's right column; layout key `flightdeck.layout.v5`); the
  strip's Run adds the compiled sweep to the queue; the Levels widget reads and edits the stand's limits
  with a reason and offers the held point after a restart; the Virtual gates widget edits a draft and saves
  it to the stand with a reason. `e2e/queue.test.ts` is new; `control.test.ts` sets its ±1 V limit on the
  stand now; `workspace.test.ts` follows the four-pane right column.
- pytest 530 passed, 4 skipped (was 520); `check_all` green; Flight Deck typecheck, 151 unit tests and all
  17 e2e tests green locally (Chrome here is the preinstalled Chromium behind a symlink at
  `/opt/google/chrome/chrome`; #135's local failures did not reproduce).

## In flight
- The PR for `step-6c/run-queue` awaits the human's merge; it closes #78 and #79 and is watched.
- **The Phantom cutover, queued, not started** (Analysis 0007; qdt #140, #141, #142; Phantom #40, #41).
  Before any qdt code it needs a step file (ADR 0071), with #141 as its first deliverable.
- Tune-ups are not queue entries yet (ADR 0086 §6); none of the T-rows needs one.
- The token is not yet in the runbook: ADR 0082 puts it where a stand server is first bound off loopback
  (the lab PC, deliverable 13).
- Open UI findings: #130, #122, #120, #119. #135 (local e2e failures) did not reproduce this session.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Agent, next session:** script the L2 rows as `bench/test_l2_orchestration.py` (`PLANNED_BY` the step
file): T-1 … T-7, each submitted as a queue entry to `qdt-server --stand` (`POST /queue`), the scope as
the sink, oracles from the proven rows of `docs/BENCH.md`, T-2 against a `StandState` limit, T-1's restart
through `/levels/pending/confirm`, T-7's reorder, remove and abort through the queue routes; checked end to
end against the simulated stand where a row allows it, as the L1 rows were. Then deliverable 11 (#76, the
`settle_s` audit), 14 (#112, a local Postgres without Docker; this session ran one with `initdb` and
`pg_ctl` as a non-root user) and 15 (#114, Windows commands). Deliverables 9–10 wait for the human's
decision on ADR 0077. Branch `step-6c/<short-name>`. Blockers from the human's machines first.
**Human:** merge this PR. On the rehearsal `qdt-db`, update the repository and run
`uv run python -m qdt_registry init` as the admin (said 2026-10-27: when back at that PC). Still open:
send plan §9 to IT; `ipconfig` on the measurement PC for #80; decide the rest of ADR 0077 before
deliverables 9–10; the runbook on the lab PC, then `bench/test_l1_remote_read.py` from a desk; review the
pre-deployment records; restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
- **2026-10-27 (session 32):** "I will re init the register when I get back to the database pc. Start
  deliverable 8."
- **2026-10-27 (session 31):** "Ok then continue with deliverable 7." After #144 was opened: "Yes, make sure
  all agent submitted PRs have a watcher armed going forward" → root `CLAUDE.md`, End step 6.
- **2026-10-27 (session 30, detour):** on Analysis 0007: "move the sequencer interpreter into qdt lab as you
  say. device file makes more sense. Let's hold off on deciding the release cadence. I don't see a decision
  needed for the simulated stand."
- **2026-10-25 (session 30):** "accept 0075" (ADR 0084); discovery starts with instruments connected
  directly to the computer, with an address range "for future specification when I understand how we can
  isolate the rack ips to a vlan or range".
- Earlier direction, verbatim: `git show d7c7a01:docs/STATUS.md`, § Direction recorded (sessions 26–30),
  and `git show b94193f:docs/STATUS.md` (sessions ≤ 25).

## Decisions pending
All are `decision` issues (`gh issue list --label decision`), plus Step 6c's remaining open decision:
ADR 0077 (before deliverables 9–10; its discovery scope is already narrowed by ADR 0084, #80). Settled:
ADR 0075 (ADR 0084) and its details (ADR 0085, 0086). Held by the human (2026-10-27): Phantom's release
cadence against qdt's pin (Analysis 0007, answer 3).
