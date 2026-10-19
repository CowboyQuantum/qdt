# 0071 — Work traces to the plan; what a session finds becomes a GitHub issue; a bench test names the plan that asked for it

**Status:** Accepted
**Date:** 2026-10-19
**Step:** process (between Step 6 and the deployment step; applies to every step after)

## Context
By session 25, work was accumulating that no step file or ADR had asked for. Five of the nine files
in `bench/` were named in no step file (`test_l2_sensor.py`, `test_l2_two_lines.py`,
`test_opx_streaming.py`, `test_scope_segments.py`, `scope_accuracy.py`); ADRs were written for some
afterwards. `docs/STATUS.md` had grown "Known broken", "Bench tasks" and "Decisions pending" sections
of about forty items. Every session rewrote them, and they had become where the next slice was
picked from, so a bug noticed in passing could turn into a bench row and then into an ADR without
the human ever ranking it against the roadmap. The repository had no GitHub issues.

On 2026-10-19 the human said: "I'm getting a little worried that you're generating bench tests and
tasks that have not been captured in an ADR or design plan", and proposed that the bugs an agent
finds be documented as GitHub issues and addressed later, according to how critical they are to the
roadmap. The human also named the roadmap goal those issues are ranked against: deployment on the lab
network (the `Deployment` milestone).

## Decision
- **Work traces to the plan.** Code a session writes traces to a deliverable or test row in the
  current step file, to an accepted ADR, or to an issue the human has labelled `roadmap` or `blocker`.
- **What a session finds becomes an issue, not a fix.** A bug, a gap, a bench idea or a pending
  decision noticed during a session is filed as a GitHub issue: what was seen, how to reproduce it,
  where in the code, and which milestone it affects. It is labelled `found-by-agent` and one of
  `blocker` / `roadmap` (with a milestone) / `backlog`, plus `bench`, `fridge` or `decision` where they
  apply. The agent's triage is a first pass that the human corrects.
- **The one exception is a blocker.** A defect that stops the current step from meeting its exit
  criterion is fixed in the session that finds it. It still gets an issue labelled `blocker`, the fix
  carries a regression test, and the commit says `Fixes #N`.
- **A bench test names the plan that asked for it.** Every `bench/test_*.py` declares
  `PLANNED_BY`: accepted ADRs (`"ADR NNNN"`) or step files that name the test file
  (`"docs/steps/<file>.md"`). `scripts/check_bench_rows.py`, run by `check_all.sh` in CI, fails
  otherwise. A new bench row is written into a step file or an ADR before its test exists.
- **STATUS.md holds no backlog.** It keeps the step, what was done, what is in flight, the next action
  and the human's direction, and links to issues for everything else. Milestones: `Deployment`,
  `Step 7 — other sources`, `Step 8 — frameworks`.

## Consequences
- Easier: the human ranks the backlog in one place, from a phone, against a milestone. A fix links to
  its issue, and the merge closes it.
- Easier: a session's scope can be checked against something written down, and for the bench that
  check is mechanical.
- Easier: STATUS.md fits on a screen again, and a fresh session reads the plan, not a wish list.
- Harder: a real defect found in passing waits for triage even when the fix is one line. The `blocker`
  exception covers only what the current step cannot exit without.
- Harder: issues live outside git, so the plan's state is split between the repo (steps, ADRs) and
  GitHub (the backlog). The repo is public, so issues obey rule 7 like any file: no serials, addresses,
  site names or tolerances.
- Must now: `/session-start` lists the open `blocker` issues and the current milestone's `roadmap`
  issues; `/session-end` files what the session found before STATUS.md is rewritten.
- Must now: the eight bench test files existing on 2026-10-19 declare `PLANNED_BY` retroactively
  (step 5's file for the L1/L2-1/L2-2/L2-3 rows; ADR 0063/0064, 0067/0069, 0070, 0015/0066 and 0065 for
  the rest). The forty STATUS.md items are issues #75–#114.

## Alternatives considered
- Keep the STATUS.md lists — rejected: rewriting them every session is what made them the source of
  unplanned slices, and they cannot be ranked, assigned or closed by a merge.
- A `BACKLOG.md` in the repo — rejected: it versions with the code, but the human triages from a phone
  and a merge cannot close a line in a file.
- Let `PLANNED_BY` cite an issue — rejected: an offline check cannot see an issue's labels, and a
  `roadmap` issue that becomes bench work should first become a row in its step file, which the check
  can see.
- No in-session fixes at all — rejected: a step that cannot exit because of a defect it found would
  wait on a triage round-trip for no gain.
