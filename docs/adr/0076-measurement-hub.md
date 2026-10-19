# 0076 — The measurement hub (stretch): leases, jobs as task DAGs, nodes that connect outward, one URL for front ends

**Status:** Proposed
**Date:** 2026-10-19
**Step:** 6c, deliverable 16 (goal 4, stretch; not an exit criterion). Builds on ADR 0074 and 0075.

## Context
Deployment goal 4: jobs submitted to the lab PC and routed to a fridge. The longer user story (human,
2026-10-16/18): any user logs into a web front end and sends jobs to a measurement hub; first, a
measurement engineer takes exclusive control of one machine and drives it; later, a fleet of machines
with no designated driver, where a submitted circuit or measurement is expanded into the calibrations it
needs and routed to a valid machine; in both, analysis and simulation may run on other compute nodes.
The human's decisions (2026-10-18): a lease expires on a timer **and** on release; a lab identity is a
login; the hub runs on the lab PC (`qdt-db`) for now. ADR 0074 gives each stand a server with a command
token and `qdt-db` a read server; ADR 0075 puts a persisted queue in each stand server.

## Decision
**Five objects, a later schema slice `scheduling.py`** (not Step 6c's slice):
- `Node(node_id, kind: stand|worker, name, capabilities, last_seen)` — a stand carries its `StandConfig`;
  a worker lists the methods / sim models it runs.
- `Lease(lease_id, stand_id, principal, acquired_at, expires_at, released_at, preempted_by, reason)` —
  exclusive control of a stand; ends on timer or release; the holder renews; an admin may preempt with
  a recorded reason. A user and the hub's scheduler hold leases the same way.
- `Job(job_id, submitted_by, lease_id, tasks, created_at, state)` — a DAG of tasks plus provenance; a run is
  a one-task job, a tune-up (ADR 0048) a multi-task job.
- `Task(task_id, kind: measure|analyze|simulate|decide, requires, inputs, depends_on, state, node_id,
  outputs)` — `requires` is capability data, so a planner generates tasks through the same model.
- `Event(job_id, task_id, kind, at, payload)` — transitions and relayed stream markers.

**Topology.** `packages/qdt-hub` is the one URL front ends use; it schedules, routes, relays and records,
and executes nothing. Stand servers (`qdt-server --hub URL`) and workers (`packages/qdt-worker`) connect
**outward** over a persistent WebSocket and take tasks on it; the hub never opens a connection to a lab
machine, so measurement PCs need no inbound rule. A stand's ADR 0075 queue is where its tasks land. A node
that loses the hub finishes its task and reconnects. Without `--hub`, the stand server behaves as in ADR 0074.

**Data.** Measurement stays one writer per stand (ADR 0024/0026). Workers write results. The hub owns its
own tables in a separate schema of the same Postgres. Workers need payloads from anywhere, so the hub
brings the HTTP upload and download endpoint (Analysis 0003 option B) that ADR 0074 deferred.

**Identity.** Hub-local logins (salted hashes; roles `admin|operator|observer`); cookie sessions for the
browser, bearer tokens for the API, per-node tokens for stands and workers. Observers subscribe; operators
hold leases and submit; admins preempt and manage. This replaces ADR 0074's command tokens for clients that
go through the hub. SSO is a later adapter behind the same roles.

**Scheduler v1** is one function: a stand runs its lease holder's jobs FIFO through its queue; a task is
ready when its inputs exist; a worker takes the oldest ready task it can run.

**Front ends** target the hub once it exists: stand selector, lease controls beside Run, job views.

## Consequences
- Easier: exclusive access and the fleet share one model; one ingress for the office subnet; stands and
  workers behind NAT; a hub restart loses nothing; analysis scales by adding workers.
- Harder: a second service with its own schema and migrations; logins in scope; a relay hop on the stream
  (measured against Analysis 0001's 50 ms budget).
- Must now (when started): the slice; the hub with leases and single-stand routing; outward registration in
  `qdt-server`; the relay; the upload endpoint; Flight Deck's hub target. Workers and the calibration
  planner follow.

## Alternatives considered
- Per-stand servers only, front ends choosing one — the ADR 0074 state; kept for Step 6c, insufficient for
  a fleet.
- A general broker or workflow engine — rejected for v1: a small task model over a few nodes; the schema
  objects must stay the API.
- The hub initiates connections to stands — rejected: inbound rules on every measurement PC.
- The hub runs `decide` tasks — rejected: keeps the hub stateless and decision provenance identical
  everywhere.
