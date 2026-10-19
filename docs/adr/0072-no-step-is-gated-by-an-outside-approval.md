# 0072 — No step is gated by an approval outside the repo

**Status:** Accepted
**Date:** 2026-10-19
**Step:** process (the plan's §7 sequencing and §12 Open Decision #5)

## Context
Plan v0.3 made Step 7 the only step gated by a manager's sign-off (Open Decision #5, "Pending as of
Oct 2026"). The plan never said what the sign-off involved or who gave it. Every session that reached
the end of a step repeated the gate, and on 2026-10-19 the roadmap's goal became deployment on the lab
network, which had been part of Step 7. The human said: "let's completely remove the manager sign-off
requirement - I don't want to hear it mentioned again."

## Decision
No step is gated by an approval outside the repo. Open Decision #5 is closed as withdrawn, and Step 7
and the deployment work are sequenced like any other step: by the human's choice, recorded in STATUS.md
and ADRs.

## Consequences
- Easier: the deployment step can be planned and started without waiting.
- Harder: nothing in the plan now marks where shared lab infrastructure begins. The work that needs IT
  (plan §9's checklist: rights on the lab PC, firewall rules, a DNS name, a backup location) remains,
  as deliverables of the step that needs it rather than as a gate in front of it.
- Must now: sessions do not raise the withdrawn gate. The plan (§7 sequencing notes, §12 row 5) and the
  Step 6 and Step 7 step files no longer name it.

## Alternatives considered
- Keep the gate and define it — rejected by the human.
- Move the gate onto the deployment step only — rejected by the human, for the same reason.
