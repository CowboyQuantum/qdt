# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** none in progress. Steps 0–6 and 6b are DONE. The roadmap goal is now **deployment on the lab
network** (milestone `Deployment`, human, 2026-10-19); it has no step file yet.
**Branch:** `docs/drop-sign-off` (PR against `main`: ADR 0072, no step gated by an outside approval; the human
merges). PRs #25–#74 and #115 (ADR 0071) merged 2026-10-14/19.
**Last session:** 2026-10-19 (session 26), no bench.

## Done this session
- **ADR 0071: work traces to the plan.** Code a session writes traces to a step file's deliverable or row, an
  accepted ADR, or a `roadmap`/`blocker` issue. Whatever a session finds becomes an issue (`found-by-agent` +
  `blocker`|`roadmap`|`backlog`, + `bench`/`fridge`/`decision`); only a blocker is fixed in-session.
  `CLAUDE.md` (Discipline, Where to look), `/session-start`, `/session-check`, `/session-end` and
  `bench/README.md` say so.
- **`scripts/check_bench_rows.py`** (in `check_all.sh`): every `bench/test_*.py` declares `PLANNED_BY` (accepted
  ADRs, or step files that name it). The eight existing files declare it retroactively.
- **Issues #75–#114:** the forty items that were this file's "Known broken", "Bench tasks", "Fridge tasks" and
  "Decisions pending", with labels and milestones. Six are on `Deployment`: #75 unreachable instrument, #76 stand
  settles, #77 `bench_step`, #78 run queue, #79 per-browser limits / held point in memory, #80 the OPX's address.
- Milestones `Deployment`, `Step 7 — other sources`, `Step 8 — frameworks`. No code outside the check changed;
  466 Python tests (+5 Postgres-parametrized), 4 skipped; Flight Deck unchanged.

## In flight
- This PR awaits the human.
- **A stale `git am` in this checkout** (`.git/rebase-apply`, 2026-10-15). It doesn't block anything.
  `git am --quit` removes it safely; `git am --abort` would move the branch back, so don't use that.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Human:** merge this PR; bring a roadmap patch from the chat instance (new roadmap goals, the deployment step) and
the unreachable-instrument proposal (#75). **Agent:** `git am --quit` (the stale patch state, below), then apply
the roadmap patch on its own branch against `main`, run `check_all.sh` and `pytest`, and open the PR. If no patch
comes, draft the deployment step file from the four goals (below). Its open decisions to start with: the payload
transport off-box (Analysis 0003 §3, ADR 0026); where the run queue lives (#78); stable names for the instruments
on the lab network (#80); where limits and the held point live (#79).

## Direction recorded (human)
- **2026-10-19 (session 26):** "I'm getting a little worried that you're generating bench tests and tasks that have
  not been captured in an ADR or design plan … document them as issues in github that we can address later
  depending on how critical they are to the roadmap goals" (ADR 0071); "the rule looks good for now. Let's file
  all those issues." **Deployment means:** (1) the registry on a database PC whose records can be read from any
  computer on the network as well as the measurement PC: Flight Deck, any Python script with the database
  address and credentials, any other application that understands the schema; (2) orchestration of a set of
  measurement tasks the human enumerates, validated on the bench through the scope; (3) manipulating measurement
  parameters and analysing scans through Flight Deck, in order to discover missing features; (4, stretch)
  submitting jobs to the lab PC and having it route each job to a fridge logically. Then: "let's completely remove
  the [outside approval] requirement" (ADR 0072: no step is gated by an approval outside the repo; do not raise it).
- **2026-10-19 (session 25):** "do we need the bench to answer the unreachable instrument issue? I have a proposal
  for that I'll discuss later" (#75); "ok let's do the dual opx line acquisition" (ADR 0070).
- **2026-10-19 (session 24):** "let's do (2), it's wired for that now" (the OPX's input as the sink, ADR 0069).
- Earlier direction (2026-10-13 to 2026-10-19, sessions ≤ 23): each item became an ADR or a merged PR; the
  verbatim record is in `git show b94193f:docs/STATUS.md`, § Direction recorded.

## Decisions pending
All are `decision` issues (`gh issue list --label decision`), apart from the deployment step's own (above).
Deliverable 4's defaults remain as taken (readback null; the limit a browser setting), now questioned by #79.
