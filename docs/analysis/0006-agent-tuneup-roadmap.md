# Analysis 0006 — An agent that tunes spin-qubit devices: the autonomy ladder (the chat's conception, 2026-10-19)

**Date:** 2026-10-19 · **Against:** `main` at `d27252f` · **Step:** none yet (proposal)
**Kind:** analysis note. Not a decision. A proposal for how a Claude agent could tune quantum-dot spin
devices on qdt, recorded before the human's review. Open questions at the end; answers recorded there.

## Framing
qdt can carry a Claude agent that tunes devices, built and improved as a **versioned agent** rather than
retrained weights. The substrate exists: typed actions (schema objects), a place to practise (`qdt-sim`),
provenance for every measurement (the registry), a decision structure (`CalibrationNode`).

A "specific instance" is a configured agent — model, system prompt, a tuning playbook as skills, qdt tools,
a case memory, an evaluation suite — named and versioned (`tuner-v1`, `tuner-v2`), improved like code:
change one thing, re-run the evals, compare. Fine-tuning Claude is not generally available today (check
Anthropic's current offerings first), so weight-level training is a late, optional phase; the decision logs
collected along the way are the data it would need.

## Principles
- **The agent operates; it doesn't control.** It decides at the node level — what to measure next, how to
  read it, what to try when something looks wrong. Deterministic code runs inner loops. Limits are enforced by
  the stand server (ADR 0075), never by the model. To the server the agent is one more desk with a token and
  a lease.
- **The agent looks at plots.** People tune stability diagrams by eye; Claude reads images. A record→image
  tool is the most valuable tool, next to the curated fits.
- **Every decision is a record.** An `AgentStep` schema object in the registry beside the measurements:
  observed records and results; belief about device state; action chosen and alternatives rejected;
  expectation and outcome; confidence. Tune-ups become auditable, replayable, comparable to an expert's.
- **The agent discovers; code keeps.** A decision the agent keeps making well becomes a `DecisionRule` in
  `qdt-tuning`. The agent takes the long tail; the deterministic path grows underneath it.

## The autonomy ladder
Each rung's eval is its gate; nothing skips a rung; the environment becomes more real only when earned.

```
 Recorded data ─┬─ A0 Narrator — explains recorded tune-ups
 (offline)      │      gate: narration judged correct on a fixed set
                └─ A1 Advisor — proposes the next action
                       gate: agreement with expert next actions; no proposal outside limits
 qdt-sim ────────  A2 Operator on the simulator — full tune-up        ◄ largest build: the failure library
                       gate: success rate and measurement count on the failure library; zero violations
 Bench ──────────  A3 Operator on the bench — drives the Step 6c task set
                       gate: bench run passes with the agent driving; refusals handled
 Real device ───┬─ A4 Supervised — approvals per action class
                │      gate: time and outcome compared with an expert on the same device
                └─ A5 Bounded autonomy — unattended within an envelope
                       gate: stop conditions hold; fleet use through the hub
```

| Rung | What the agent does | What gets built |
|---|---|---|
| A0 Narrator | Reads tune-up records and outcomes; explains them | `qdt-mcp` read-only tools; record-to-image tool; `AgentStep` slice |
| A1 Advisor | Proposes the next action from the records so far | Replay benchmark (simulated; internally historical) scored against the expert's next step |
| A2 Operator, simulator | Full tune-up on `qdt-sim`: pinch-offs, sensor, double-dot regime, charge states, virtual gates | The failure library in `qdt-sim`; scenario suite with ground truth |
| A3 Operator, bench | Drives T-1…T-7 through the same tools | Nothing new: Step 6c's queue, limits, token, discovery |
| A4 Supervised, device | Tunes a real device; approvals for action classes (large accumulation voltages, ohmic bias, anything thermal) | Approval channel in Flight Deck; per-class policy in stand state |
| A5 Bounded autonomy | Unattended within an envelope, with stop conditions | Rules codified from repeated decisions; optional fine-tuning on A1–A4 logs; the hub |

## What the instance is made of
| Part | What it is | Where it lives |
|---|---|---|
| Tools | `qdt-mcp` over the server API: inventory, stand state, compile, run (lease/token), record summaries, plot render, methods, outcomes, write `AgentStep` | Public repo |
| Playbook | Skills encoding the human's tuning knowledge: stages, expected plots, failure signatures and responses, when to stop and ask | Generic public; device/site heuristics internal (rule 7) |
| Memory | Case library of tune-ups with `AgentStep` logs, by device type and symptom | Registry |
| Harness | Claude Code interactively; Agent SDK headless for benchmarks and unattended runs; `jig`'s protocol with a campaign as the unit of work | `jig` + a runner |
| Evals | A1 replay set and A2 scenario suite, in CI on every change to prompt, skills or tools | Public (scenarios); internal (historical) |

## The bottleneck, and the link to Step 6c
Simulator fidelity, not the model: an agent tested on clean honeycombs learns clean honeycombs. The A2
failure library — switching, drift, charge noise, unintentional dots, leaky barriers, sensor detuning,
latching — is the largest build and where the human's experience counts most. Existing ML autotuning
(charge-state classifiers, embedding-based fine-tuning; Moon et al. 2020, Nature Communications) fits as tools
the agent calls; the agent adds orchestration, explanation and the unexpected. Step 6c builds A3's
prerequisites; the hub's leases give the agent a principal; A0–A1 need only the MCP server, the plot tool and
the `AgentStep` slice, and can start against simulator records now.

## Open questions (settled in review; answers recorded below)
1. A qdt step after 6c, a separate Cowboy Quantum repo, or tools in qdt with agent and playbook elsewhere?
2. Which action classes need approval at A4; per action or per campaign?
3. Success thresholds that end A1 and A2.
4. Historical tune-ups as an internal replay set; who curates them?
5. First artefact: the failure library spec or the `AgentStep` schema?

### Answers (human, 2026-10-22)
1. **Where it lives: a fully separate repo, `autopilot`, that reaches qdt only through its API.** This
   supersedes the split this note proposed (`qdt-mcp` and `AgentStep` inside qdt). Consequences:
   - qdt stays model-agnostic; its versioned HTTP API (ADR 0074's read contract plus the stand server's
     command API) is the only coupling, so it must be documented and versioned as a public contract.
   - The MCP tool server, `AgentStep`, the record-to-image rendering (from payload bytes fetched over HTTP),
     case memory, evals, the runner and the approval interface all live in `autopilot`, with its own store
     for agent records that refer to qdt record ids.
   - What `autopilot` needs from qdt, all through the API: the read server and command token (0074), the
     server-side queue and limits (0075), discovery (0077), and simulated stands whose fault scenarios can
     be selected per run — the failure library itself is physics and belongs in `qdt-sim`.
   - Site-specific playbook material and historical replays stay out of both public repos.
2. **Approvals at A4: every action**, per action. A4 needs a way to approve a planned sequence in one
   decision so a sweep campaign is not dozens of clicks; each approval still records who and when.
3. **Thresholds (starting values, to revisit):** A1 ends at agreement with the human's next action on 80% of
   a 50-step replay set; A2 at 90% success over the failure library, zero limit violations, and a measurement
   count within 2× of the deterministic tune-up.
4. **Historical replays:** yes, internal only, curated by the human, starting with about ten tune-ups whose
   outcomes are well remembered.
5. **First artefact:** open. Recommendation: `AgentStep` first, in `autopilot` (small; unblocks A0 and A1
   against qdt's existing API and records), with the failure-library spec written in parallel for `qdt-sim`.
