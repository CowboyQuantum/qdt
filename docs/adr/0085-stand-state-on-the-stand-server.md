# 0085 — The stand state on the stand server: what a limit covers, when a version is written, and how a held point is offered after a restart

**Status:** Accepted
**Date:** 2026-10-27
**Step:** 6c (deliverable 7; implements ADR 0075 as accepted by ADR 0084; issue #79)

## Context
ADR 0075, accepted as written by ADR 0084, moves a stand's voltage limits, its coupling matrix and its
held operating point out of the browser and into versioned stand state that the stand server enforces.
It names the schema (`ChannelLimit`, `StandState`, `QueuedRun`), says the latest version is in force,
says a level or a compiled sweep beyond a limit is refused and never clamped, and says the held point is
re-applied after a restart only when a person confirms it. Building it raised questions the ADR does not
answer, each of which a future session could reasonably ask about:
- which levels of a sweep a limit is checked against, given pulse sequences, coupled axes and
  hand-written sequencer programs;
- which changes write a version, and who the version names as its author;
- what the server does between a restart and the confirmation, including when someone sets a level first;
- how a stand server whose registry cache is new (a rebuilt computer, or a second computer for the same
  stand) avoids writing a version 1 that collides with the history already on the database PC (`qdt-db`);
- why `QueuedRun` is not in this slice yet, although ADR 0075 lists it.

## Decision
1. **The schema.** `qdt_schemas.operations` holds `ChannelLimit(channel, min_v, max_v)`, a closed range
   of finite numbers in the SI unit of the channel's quantity (the `_v` suffix of ADR 0075 is kept; a
   current channel's limit is in amperes), and `StandState(stand_id, version, limits, couplings, held,
   set_by, set_at, reason)`. The held point is a tuple of `FixedLevel`s, the shape `GET /levels` already
   returns: ADR 0075 wrote `ChannelLevel`, but that type carries live setpoints and readbacks and is
   never stored. A state refuses to exist with two limits or two held levels on one channel, a channel
   coupled to itself, a coupling that is not a finite number, or a held level outside its own limit.
   `StandState` is a persisted type with a version 1 fixture. **`QueuedRun` enters with deliverable 8**,
   in the same commit as the queue that consumes it (CLAUDE.md: a schema change is one commit with its
   consumers): its `request` field needs `RunRequest`, which today is a model local to `qdt-server`, and
   moving that into `qdt-schemas` belongs to the same change.
2. **The registry.** Versions are rows of a new table, `stand_states`, keyed by `(stand_id, version)`
   (DDL version 4, an additive upgrade from version 3). A cache accepts version 1 for a stand it holds
   nothing of and otherwise only the next version; a different body under a stored version is refused.
   Sync uploads stand states last, so a stand that two caches claim cannot hold back the records. At
   start, before loading its state, a stand server copies the registry server's versions of its stand
   into its cache (`Registry.pull_stand_states`), waiting at most 10 seconds; unreachable, it logs and
   continues from its own cache, as a sync does (ADR 0080). The read server serves the history at
   `GET /stand-states`.
3. **What a limit is checked against.** A limit bounds the levels its own logical channel is programmed
   to. The compiler (`qdt_lab.experiment.check_limits`, called by `compile_sweep` when given a state)
   counts the operating point; every stepped or triggered axis from `start` to `stop`; every coupled
   companion from its origin plus the coupling times the axis's range, as the executor moves it; and,
   in a pulse sequence, every `step` level, both ends of every `ramp` and plus or minus every `drive`
   amplitude, each symbol over the range its binding gives. Every value is linear in its axis, so the
   extremes are exact. A pulse line and the DC line it is summed with through a bias tee are limited
   separately, because the stand file does not say which line feeds which gate. A hand-written program
   declares no levels, so it is refused on a sequencer that carries a limited channel. A limit may only
   name a channel some instrument drives; a coupling only links LevelSource channels.
4. **Where a refusal happens.** A `POST /levels` beyond a limit is refused whole: nothing is applied
   and no version is written. A tune-up node whose held outputs exceed a limit fails the tune-up. A
   compile or a run submission beyond a limit is refused with a 400 that names every channel, the levels
   it would reach and its limit. A queued run is checked again when it starts, so a limit tightened
   while it waited fails it, unrun. New limits that would put the held point (held or offered) out of
   bounds are refused: lower or release the level first.
5. **When a version is written, and by whom.** A version is written at a stand's first start (version 1,
   no limits, `set_by` `qdt-server`), at every level set or release, at every change of limits or
   couplings (`POST /stand/state`, which requires a reason), and when an offered held point is
   discarded. Confirming writes nothing, because the state does not change. `set_by` is the label of the
   command token the change came with, `local` for a command from the stand server's own computer, or
   `tune-up <id>` for a node that holds its outputs; the server takes it from the token check, never
   from the request body.
6. **After a restart.** The latest version's limits and couplings are in force at once. Its held point
   is offered (`GET /levels/pending`), not applied and not held, so no sweep inherits it until a person
   confirms it (`POST /levels/pending/confirm`, which applies and holds it) or discards it
   (`DELETE /levels/pending`, which writes a version holding nothing). Setting or releasing a level
   before deciding discards the offer the same way, and the new version's reason says what was not
   re-applied. Runs may run in the meantime without the held point, as every run did after a restart
   before ADR 0075.
7. **Flight Deck switches in deliverable 8.** The Levels widget's limit, the Virtual gates widget's
   matrix and a confirmation prompt for an offered held point move to these routes together with the
   queue widget. Until then a browser's own limit is an extra check in front of the server's, and the
   server's limit is the one that holds.

## Consequences
- Easier: one set of limits per stand, enforced on every path that drives a level (click-to-set,
  compile, submission, the start of a queued run, a tune-up's held outputs), each refusal naming the
  channel and its limit; an audit trail of who changed the stand and why, readable from the database PC
  when the measurement computer is off; a restart keeps the limits and loses no held point.
- Harder: every click-to-set writes a registry row (small, and the audit trail is the point); a stand
  served from two computers at once under one `stand_id` conflicts on sync, which is logged and leaves
  that stand's states unsynced, never the records; a pulse line's limit must be set apart from its DC
  line's.
- Must now: deliverable 8 adds `QueuedRun` with `RunRequest` moved into `qdt-schemas`, the persisted
  queue, and Flight Deck's Levels, Virtual gates and queue widgets on these routes, including the
  confirmation prompt; issue #79 closes with it (ADR 0084). The slice is frozen at the step's exit.

## Alternatives considered
- Clamp a level to its limit — rejected by ADR 0075: the driver rule is refuse, never clamp, so a
  person sees that the stand did not do what was asked.
- Write a version when a held point is confirmed — rejected: the state does not change, and a version
  per restart would bury the changes that matter; the server logs the confirmation.
- Refuse every level set while a held point is offered — rejected: Flight Deck cannot show the offer
  until deliverable 8, so a restart would lock the Levels widget; a set is a deliberate act on named
  channels, and discarding the rest of the offer moves nothing.
- Take `set_by` from the request body — rejected: the token check already knows which desk sent the
  command, and a body field could name anyone.
- Infer the bias-tee pairing of pulse and DC lines from channel names — rejected: names are a
  convention of the simulated stand, not a fact the stand file declares.
- Pull the registry server's history on every write instead of at start — rejected: a write would then
  wait on the network, and a stand server must keep working when `qdt-db` is away (ADR 0080).
