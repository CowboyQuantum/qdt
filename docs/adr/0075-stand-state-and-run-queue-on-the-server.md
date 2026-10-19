# 0075 — Limits, couplings and the held operating point are stand state on the server, persisted and versioned; the run queue lives in the stand server

**Status:** Proposed
**Date:** 2026-10-19
**Step:** 6c (issues #78, #79; extends ADR 0053, 0057, 0061)

## Context
Issue #79: the Levels widget's voltage limits and the Virtual gates coupling matrix are browser settings
(ADR 0057), and the held operating point (`/levels`, ADR 0053) lives in server memory and is lost on
restart. With Flight Deck opened from several desks, two browsers can hold different limits for one
stand; a limit is a safety setting. Issue #78: the run queue (ADR 0061) lives in the browser and cannot
be reordered. Deployment goal 2 is orchestration of an enumerated set of tasks; goal 4 routes jobs to a
fridge. Both need the queue where the stand is.

## Decision
**Schema slice for Step 6c, `operations.py`** (every field with `description=`):
- `ChannelLimit(channel, min_v, max_v)` — the allowed range for one logical channel.
- `StandState(stand_id, version, limits, couplings, held, set_by, set_at, reason)` — the safety and
  operating state of one stand: per-channel limits, the coupling matrix (the shape ADR 0049 already uses),
  and the held operating point (`ChannelLevel`s). Append-only: every change writes a new version with who
  set it and why; the latest version is in force.
- `QueuedRun(queue_id, stand_id, position, request, submitted_by, submitted_at, state, run_id)` — one entry
  in a stand's queue; `request` is the existing `RunRequest` (or a tune-up request); `state` is
  `queued|running|done|aborted|failed`; `run_id` links to the `Run` once started.

**Where they live.** `StandState` versions are registry records (one more table set; the stand server
writes, the read server reads). The stand server loads the latest version at start, enforces its limits
on every level and every compiled sweep (refusing, never clamping — the driver rule), and re-applies the
held point after a restart only when the human confirms it in Flight Deck. The queue is the stand
server's: persisted in its registry cache so a restart keeps it, executed in order, one run at a time;
entries can be reordered, removed while queued, and aborted while running. Flight Deck's queue (ADR
0061) becomes a view of it. Limits and couplings are no longer browser settings; a desk changes them
through the stand server (a command, so it needs the ADR 0074 token).

## Consequences
- Easier: one limit per stand, auditable; a restart loses neither the held point nor the queue; the
  enumerated task set of goal 2 is a queue the server runs unattended; the hub (ADR 0076) generalises a
  queue that already exists.
- Harder: a new table set and migration; the compiler must see the limits (a compile against stale state
  is refused); Flight Deck's Levels, Virtual gates and queue widgets switch their source.
- Must now: L0 tests for limit refusal on levels and on compile, versioned state round trip, queue order
  through reorder/remove/abort, and queue survival across a server restart.

## Alternatives considered
- Keep limits per browser and add a server-side cap — rejected: two sources of truth for a safety setting.
- A queue in the browser that submits one at a time — rejected: closing the tab stops the work, and the
  stretch goal's routing has nothing to route.
- Re-apply the held point automatically after restart — rejected: an unattended restart should not drive
  gates without a person confirming the state the stand is in.
