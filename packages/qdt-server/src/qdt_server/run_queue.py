"""The run queue in the stand server (ADR 0075, 0086): ordered entries that the server runs one at a time,
kept in the registry's cache so a restart keeps them.

An entry waits with a position (0 runs next), may be moved or removed while it waits, runs through the
`RunManager` (so the limits in force are checked again when it starts, ADR 0085), and ends done, aborted
or failed with the run and record it became. A running entry may be aborted. The queue may be paused: it
then starts nothing new, and the entry running finishes. After a restart with entries waiting, the queue
comes back paused, because an unattended restart should not drive the stand (ADR 0075): a person resumes
it. An entry that was running when the server stopped is recorded as aborted.

`POST /runs` still starts a run directly (scripts, tune-ups); such a run takes the stand's one slot in
turn with the queue's, behind the `RunManager`'s lock, so one run at a time holds for both.
"""

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from qdt_registry import Registry
from qdt_schemas.control import RunRequest
from qdt_schemas.operations import QueuedRun, StandQueue

from .runs import RunManager

log = logging.getLogger(__name__)

FINISHED_SHOWN = 20
"""How many finished entries a `StandQueue` lists, newest first."""
FINISHED_KEPT = 100
"""How many finished entries the cache keeps; older ones are dropped (their records stay)."""
OUTCOME = {"completed": "done", "aborted": "aborted", "failed": "failed"}
"""A run's end state → its queue entry's."""


class QueueError(Exception):
    """A queue command that does not fit the entry's state (the route answers 409)."""


class RunQueue:
    """One stand's run queue: the entries, the paused flag and the worker that runs them."""

    def __init__(self, runs: RunManager, registry: Registry, stand_id: str) -> None:
        self.runs, self.registry, self.stand_id = runs, registry, stand_id
        self._entries: dict[str, QueuedRun] = {
            e.queue_id: e for e in registry.queue_entries(stand_id)
        }
        now = datetime.now(UTC)
        stopped = [e for e in self._entries.values() if e.state == "running"]
        for e in stopped:
            self._entries[e.queue_id] = e.model_copy(
                update={
                    "state": "aborted",
                    "finished_at": now,
                    "message": "the stand server stopped while this entry ran; whatever it "
                    "recorded before that is in the registry",
                }
            )
        if self._renumber() or stopped:
            self.registry.queue_put(*self._entries.values())
        waiting = len(self._waiting())
        self.paused = waiting > 0
        self.note = (
            f"the stand server restarted with {waiting} entr{'y' if waiting == 1 else 'ies'} "
            "waiting: resume the queue to run them"
            if waiting
            else ""
        )
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # --- lifecycle -------------------------------------------------------------------------------

    def start(self) -> None:
        """Start the worker (in the server's event loop)."""
        self._task = asyncio.create_task(self._work())
        self._wake.set()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    # --- what the routes call (all in the event loop, so nothing here races the worker) ----------

    def view(self) -> StandQueue:
        running = [e for e in self._entries.values() if e.state == "running"]
        finished = sorted(
            (e for e in self._entries.values() if e.state in OUTCOME.values()),
            key=lambda e: e.finished_at or e.submitted_at,
            reverse=True,
        )
        return StandQueue(
            stand_id=self.stand_id,
            paused=self.paused,
            note=self.note if self.paused else "",
            entries=(*running, *self._waiting(), *finished[:FINISHED_SHOWN]),
        )

    def submit(self, request: RunRequest, *, by: str) -> QueuedRun:
        """Add `request` at the end of the queue. It is compiled now, so a sweep the stand cannot run,
        or one beyond a limit, is refused (ValueError, KeyError) before it waits; it is checked again
        when it starts."""
        self.runs.compile(request.definition)
        entry = QueuedRun(
            queue_id=uuid.uuid4().hex,
            stand_id=self.stand_id,
            position=len(self._waiting()),
            request=request,
            submitted_by=by,
            submitted_at=datetime.now(UTC),
            state="queued",
        )
        self._entries[entry.queue_id] = entry
        self.registry.queue_put(entry)
        self._wake.set()
        return entry

    def move(self, queue_id: str, position: int) -> StandQueue:
        """Put a waiting entry at `position` (0 runs next); the others keep their order around it."""
        entry = self._waiting_entry(queue_id, "moved")
        waiting = [e for e in self._waiting() if e.queue_id != queue_id]
        if not 0 <= position <= len(waiting):
            raise ValueError(f"position {position} is outside 0 to {len(waiting)}")
        waiting.insert(position, entry)
        self._put_waiting(waiting)
        return self.view()

    def remove(self, queue_id: str) -> StandQueue:
        """Take a waiting entry out of the queue: it never runs."""
        self._waiting_entry(queue_id, "removed")
        del self._entries[queue_id]
        self.registry.queue_drop(queue_id)
        self._put_waiting(self._waiting())
        return self.view()

    def abort(self, queue_id: str) -> StandQueue:
        """Stop the running entry: its run stops between frames and is recorded as aborted."""
        entry = self._entry(queue_id)
        if entry.state != "running":
            raise QueueError(
                f"entry {queue_id!r} is {entry.state}: only a running entry is aborted "
                "(a waiting one is removed)"
            )
        if entry.run_id is not None:
            with contextlib.suppress(ValueError):  # it ended in the meantime
                self.runs.abort(entry.run_id)
        return self.view()

    def pause(self, *, by: str) -> StandQueue:
        """Start no further entry; the one running finishes."""
        self.paused, self.note = True, f"paused by {by}"
        return self.view()

    def resume(self) -> StandQueue:
        self.paused, self.note = False, ""
        self._wake.set()
        return self.view()

    # --- the worker ------------------------------------------------------------------------------

    async def _work(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while not self.paused and (waiting := self._waiting()):
                try:
                    await self._run(waiting[0])
                except Exception as e:  # never a silent stop: pause and say why
                    log.exception("the run queue stopped")
                    self.paused, self.note = True, f"the queue stopped on an error: {e}"

    async def _run(self, entry: QueuedRun) -> None:
        now = datetime.now(UTC)
        entry = self._update(entry, state="running", position=None, started_at=now)
        self._put_waiting(self._waiting())
        try:
            run = await self.runs.start(entry.request.definition, dict(entry.request.options))
        except (ValueError, KeyError) as e:  # the stand state changed since it was queued
            self._finish(entry, "failed", message=f"not started: {e}")
            return
        except Exception as e:
            log.exception("queue entry %s could not start", entry.queue_id)
            self._finish(entry, "failed", message=f"not started: {type(e).__name__}: {e}")
            return
        entry = self._update(entry, run_id=run.run_id)
        run = await self.runs.wait(run.run_id)
        state = OUTCOME[run.state]
        message = run.error or ("aborted while it ran" if state == "aborted" else "")
        self._finish(entry, state, message=message, record_id=run.record_id)

    # --- internals -------------------------------------------------------------------------------

    def _waiting(self) -> list[QueuedRun]:
        return sorted(
            (e for e in self._entries.values() if e.state == "queued"),
            key=lambda e: (e.position, e.submitted_at),
        )

    def _entry(self, queue_id: str) -> QueuedRun:
        try:
            return self._entries[queue_id]
        except KeyError:
            raise KeyError(f"no queue entry {queue_id!r}") from None

    def _waiting_entry(self, queue_id: str, what: str) -> QueuedRun:
        entry = self._entry(queue_id)
        if entry.state != "queued":
            raise QueueError(f"entry {queue_id!r} is {entry.state}: only a waiting entry is {what}")
        return entry

    def _renumber(self) -> bool:
        """Positions 0, 1, 2, … in the current order; True when any changed."""
        changed = False
        for i, e in enumerate(self._waiting()):
            if e.position != i:
                self._entries[e.queue_id] = e.model_copy(update={"position": i})
                changed = True
        return changed

    def _put_waiting(self, ordered: list[QueuedRun]) -> None:
        """Number `ordered` 0, 1, 2, … and store the ones whose position changed."""
        moved = []
        for i, e in enumerate(ordered):
            if e.position != i:
                e = e.model_copy(update={"position": i})
                self._entries[e.queue_id] = e
                moved.append(e)
        if moved:
            self.registry.queue_put(*moved)

    def _update(self, entry: QueuedRun, **update: Any) -> QueuedRun:
        entry = QueuedRun.model_validate(entry.model_dump() | update)
        self._entries[entry.queue_id] = entry
        self.registry.queue_put(entry)
        return entry

    def _finish(self, entry: QueuedRun, state: str, **update: Any) -> None:
        self._update(entry, state=state, finished_at=datetime.now(UTC), **update)
        finished = sorted(
            (e for e in self._entries.values() if e.state in OUTCOME.values()),
            key=lambda e: e.finished_at or e.submitted_at,
            reverse=True,
        )
        for old in finished[FINISHED_KEPT:]:
            del self._entries[old.queue_id]
            self.registry.queue_drop(old.queue_id)
