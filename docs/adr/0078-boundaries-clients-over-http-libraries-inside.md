# 0078 — Boundaries: clients of the lab live in their own repos over HTTP; code that runs where the hardware or compute is stays inside qdt behind enforced seams; nothing is extracted now

**Status:** Proposed
**Date:** 2026-10-22
**Step:** process (applies from 6c onward)

## Context
On 2026-10-22 the human asked, for several parts in turn, whether they should become separate repos with
slow-moving APIs: the physics simulator, the instrument layer, and Flight Deck; and where an agent that
tunes devices (`autopilot`, Analysis 0006) should live. Two kinds of boundary were distinguished:
- a **service boundary** (HTTP, the stand and read servers of ADR 0074) for anything that acts on a lab
  from elsewhere and must be refused when it is wrong — it buys isolation, remoteness and multiple users;
- a **library boundary** (an in-process Python API) for anything that runs where the hardware or the
  compute physically is — drivers are stateful, timing-coupled and latency-sensitive, and HTTP in the middle
  makes "who holds the instrument" a distributed-systems problem.
Flight Deck is already on the far side of the service boundary (rule 8; generated types). The instrument
layer and the physics core have no second consumer yet. The human's decision: keep everything in qdt for
now with the split in view; `autopilot` begins much later, in its own repo, with minimal consideration in qdt.

## Decision
1. **Rule.** Clients of the lab live in their own repos and reach qdt only through its HTTP API. Code that
   runs where the hardware or the compute is stays inside qdt as a library until something else imports it.
2. **Map, for the long term.**

   | Component | Where | Why |
   |---|---|---|
   | `autopilot` (Analysis 0006) | Separate repo, created when its work begins | A client of the lab |
   | `dispatch` — circuit design and compile to calibrated pulses, with a choice of backend | Separate repo, when the §10 pulse primitives exist (frames first) | A client of the lab: reads calibrations, submits through the API |
   | Flight Deck | Separate repo, after Step 6c | A client of the lab; already true in code |
   | Instrument layer (`qdt-lab` protocols, drivers, transports, emulators, conformance, discovery, pool) | Inside qdt behind an enforced seam | Runs where the hardware is; no second consumer yet |
   | Physics core (`qdt-sim` model, sensor, noise, fault models; later `phantom`, with charge and spin layers in one package) | Inside qdt behind an enforced seam | Runs where the compute is; no second consumer yet |
   | Measurement hub (`qdt-hub`, to be named `tower`; ADR 0076) | Inside qdt until it earns a repo by this rule | Runs where the lab's state is |
   | `jig` | Separate, personal account | Not about qdt |

3. **Nothing moves now.** No extraction is scheduled. The seams are drawn inside qdt as they are touched:
   the physics core and the instrument layer become modules that import nothing from the rest of qdt
   (their own small config types; qdt adapters map schema objects onto them), enforced by
   `scripts/check_imports.py` like rule 1.
4. **Flight Deck extraction waits for Step 6c**, when ADR 0074 has made the API a versioned public contract
   and 0075/0077 have added their endpoints. Its preconditions, done in qdt first: published `openapi.json`
   and JSON Schema bundles per release with a deprecation rule; an e2e smoke test in qdt against the last
   released Flight Deck; `--ui` serving a built bundle; CORS and a configurable API base.
5. **What qdt keeps in mind for `autopilot`, and no more:** the API stays the only coupling and is
   versioned; simulated stands will one day need a sim-control endpoint (create a stand from a fault
   configuration and seed, behind its own token) — not built until asked; fault models live in `qdt-sim`
   and the physics core's reproducibility contract (seed + model version → identical output) is written
   as if public. `AgentStep`, tool servers, rendering for agents, approvals and evals are `autopilot`'s.

6. **Names.** The fleet is named for an airfield's places and roles: Flight Deck (what you see and drive),
   Dispatch (the circuit written for this device), Tower (who may use which stand, and the queue), Autopilot
   (runs without you), Phantom (the stand-in device), Jig (how the work is done). `dispatch`'s simulated
   backend is `phantom`'s spin layer on its charge layer, not a separate simulator; an ideal gate-level
   simulator may bypass qdt, but the compile is checked only through qdt against `phantom`.

## Consequences
- Easier: one repo and one CI while the API churns through 6c; the same seams serve any future consumer;
  extraction later is a move, not a redesign.
- Harder: the two internal seams cost a refactor of driver factories (own config types) when drawn; a
  temptation to add agent-specific features to qdt must be refused by pointing at this ADR.
- Must now: add the two seams to `check_imports.py` when the modules are touched; include the Flight Deck
  preconditions in Step 6c's follow-ups; record the sim-control endpoint as a future issue, not a deliverable.

## Alternatives considered
- Extract the instrument layer and physics core now as slow-API libraries — rejected: no second consumer;
  fault models are about to churn; qdt's golden files depend on simulator determinism, so cross-repo
  physics changes would cost a version bump each.
- Extract Flight Deck now — rejected: the API is about to change through 6c; every change would cost two
  PRs during exactly the period it changes most.
- Build `autopilot` scaffolding inside qdt — rejected by the human: qdt stays model-agnostic.
