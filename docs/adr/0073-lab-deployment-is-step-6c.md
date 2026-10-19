# 0073 — Lab deployment is Step 6c, inserted before Step 7; Step 7 keeps the other sources

**Status:** Accepted
**Date:** 2026-10-19
**Step:** process (the plan's §7.2 order; Step 7's scope)

## Context
On 2026-10-19 the human made deployment on the lab network the roadmap's goal (milestone `Deployment`,
issues #75–#80, ADR 0071) and stated four goals: (1) the registry on a database PC, readable from any
networked computer as well as the measurement PC — Flight Deck, a Python script with the address and
credentials, any schema-aware application; (2) orchestration of an enumerated set of measurement tasks,
validated on the bench through the scope; (3) measurement parameters and scan analysis through Flight
Deck, to discover missing features; (4, stretch) jobs submitted to the lab PC and routed to a fridge.
Lab deployment sat inside Step 7 beside the telemetry ingest, the CI register and the internal extension
package. ADR 0072 removed the outside approval that held Step 7, and noted that IT work becomes a
deliverable of the step that needs it. Renumbering Steps 7–8 would make every merged ADR that says
"Step 7" (ADR 0051 for telemetry, among others) wrong; ADR 0032 set the precedent of inserting a lettered
step instead (4b).

## Decision
Insert **Step 6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`) after 6b and before Step 7.
It owns the four goals, the plan §9 IT checklist, plan Open Decision #6 (lab PC OS) and the `Deployment`
milestone. Step 7 keeps the cryo context ingest, the CI register, the internal extension package and the
pilot demonstration; its lab-PC and IT lines move to 6c. Steps 7 and 8 keep their numbers.

## Consequences
- Easier: every merged reference to Step 7 or 8 stays true; the deployment step has a file a session can read.
- Harder: three lettered steps (4b, 6b, 6c) sit in a numbered sequence; the index carries their order.
- Must now: `docs/steps/README.md` and plan §7.2 list 6c; plan §9's header and §12 row 6 point at 6c;
  Step 7's goal, deliverables and open decisions drop the lab-PC and IT lines.

## Alternatives considered
- Deployment as Step 7, other sources renumbered to 8 and frameworks to 9 — rejected: breaks merged ADRs'
  step references, which may not be edited (ADRs are immutable).
- Deployment inside Step 7 — rejected: the human's goals are a step of their own with their own exit, and
  Step 7's other content does not depend on them.
