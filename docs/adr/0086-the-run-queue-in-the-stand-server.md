# 0086 — The run queue in the stand server: entries kept in the cache, paused after a restart with entries waiting; Flight Deck's queue, Levels and Virtual gates widgets on the server

**Status:** Accepted
**Date:** 2026-10-27
**Step:** 6c (deliverable 8; implements ADR 0075 as accepted by ADR 0084; issues #78, #79)

## Context
ADR 0075, accepted as written by ADR 0084, moves the run queue into the stand server: persisted in its
registry cache so a restart keeps it, executed in order, one run at a time, with entries reordered or
removed while queued and aborted while running. Flight Deck's queue, which ADR 0061 kept in the browser,
becomes a view of it. ADR 0085 put the limits, the coupling matrix and the held point on the server and
left Flight Deck's widgets to this deliverable. Building it raised questions a future session could ask:
- the registry is append-only, and a queue entry changes as it moves, so where is it kept;
- what the server does with waiting entries after a restart, given ADR 0075's principle that an
  unattended restart should not drive the stand;
- how `POST /runs`, tune-ups and the queue share the one stand;
- why `QueuedRun` carries fields ADR 0075 does not list, and why a tune-up is not yet a queue entry;
- how the Levels and Virtual gates widgets change state that is now the stand's.

## Decision
1. **The schema.** `qdt_schemas.operations.QueuedRun` has ADR 0075's fields (`queue_id`, `stand_id`,
   `position`, `request`, `submitted_by`, `submitted_at`, `state`, `run_id`) and four more, because a
   restart forgets the `Run` while the entry survives: `record_id`, `started_at`, `finished_at` and
   `message`. `position` is the place among the waiting entries (0 runs next) and is null once the entry
   has left the queue. `state` is ADR 0075's `queued`, `running`, `done`, `aborted` or `failed`; a removed
   entry is deleted, because it never ran. `StandQueue(stand_id, paused, note, entries)` is the queue as
   the server reports it: the running entry, then the waiting ones in order, then the latest finished.
   `RunRequest` moved from `qdt_server.app` into `qdt_schemas.control`, so the entry can keep it; its
   body is unchanged for every caller. `QueuedRun` is a persisted type with a version 1 fixture.
2. **Where entries are kept.** In a second cache-local table, `run_queue`, beside `sync_state`: operating
   state, rewritten as an entry moves, never synced, not part of the shared table layout (no DDL change).
   The registry's append-only rule keeps one stated exception more. What a queued run produces, the
   record, is as durable as ever. The cache keeps the latest 100 finished entries and the queue lists 20.
3. **How it runs.** A worker in the server's event loop takes the entry at position 0 when the queue is
   not paused, marks it running, starts its run through the `RunManager` (so the limits in force are
   checked again then, ADR 0085), waits for the run to end, and records how it ended. One entry runs at a
   time. `POST /runs` stays for scripts, the bench rows and tune-ups; such a run takes the stand's one
   slot in turn with the queue's, behind the `RunManager`'s lock, so one run at a time holds for both. An
   entry may be running while its run waits for that slot.
4. **The commands.** `POST /queue` adds a `RunRequest` at the end and compiles it at once, so a sweep the
   stand cannot run, or one beyond a limit, is refused before it waits. A waiting entry can be moved
   (`POST /queue/{id}/move`) or removed (`DELETE /queue/{id}`); the running one can be aborted
   (`POST /queue/{id}/abort`); the queue can be paused and resumed. A command on an entry in the wrong
   state answers 409. Every queue route is on the stand router, so its commands need the token off
   loopback, and `submitted_by` comes from the token's label as `set_by` does (ADR 0085). The routes run
   in the event loop, as the worker does, so none of them races it.
5. **After a restart.** Waiting entries come back in their order, and if there are any the queue comes
   back paused, with a note saying so, until a person resumes it. An entry that was running when the
   server stopped is recorded as aborted, with a message.
6. **Tune-ups are not queue entries yet.** ADR 0075 allows a tune-up request as an entry. None of the
   step's rows submits one (T-1 to T-7 and W-1 queue sweeps), and a tune-up already runs its nodes one
   run at a time through the `RunManager`. A tune-up entry is added when a row or the human asks for it.
7. **Flight Deck.** A Queue widget shows the server's queue and sends its commands; it is in the default
   layout's right column (the layout key moves to version 5 so browsers pick it up). The strip's Run adds
   the compiled sweep to the queue and follows the entry until it becomes a run. The Levels widget reads
   each channel's limit from the stand state, sets or removes one with a reason, refuses a level beyond
   it (the server refuses it too), and shows a banner to re-apply or discard the held point offered after
   a restart; the browser's own limit is gone. The Virtual gates widget reads the matrix from the stand
   state; an edit is a draft until it is saved with a reason, sweeps take the saved matrix, and a
   tune-up's coefficients go into the draft. Against a read server none of these widgets exists.

## Consequences
- Easier: a queue that survives closing the browser and restarting the server, ordered from any desk;
  limits and couplings that every desk sees alike; the T-rows (T-1 … T-7) can submit queue entries to
  the stand server; issues #78 and #79 close.
- Harder: the registry has two mutable cache tables to reason about instead of one; a restart with
  entries waiting needs a person to resume; the right column holds four panes by default, which is
  tight on a short screen (each table keeps a minimum height and its pane scrolls).
- Must now: the T-rows submit through `POST /queue`; a tune-up entry, if a row asks for one, extends
  `QueuedRun.request`; the slice is frozen at the step's exit.

## Alternatives considered
- Keep the queue as append-only events in the shared registry — rejected: the queue is operating state
  of one stand server, nobody else reads it, and an event log adds machinery whose only product is the
  current order; the records stay the durable output.
- Run waiting entries automatically after a restart — rejected by ADR 0075's principle: an unattended
  restart should not drive the stand, and a run would start without the held point it was queued under.
- Route `POST /runs` through the queue — rejected for now: tune-ups, scripts and the bench rows use it,
  and the lock already keeps one run at a time; the queue is the ordered, persisted path people use.
- Save every edit of the coupling matrix as it is typed — rejected: a version per keystroke would bury
  the changes that matter, and a half-typed matrix would reach the next sweep.
