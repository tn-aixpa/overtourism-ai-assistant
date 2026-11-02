# SPDX-License-Identifier: Apache-2.0
"""
Per-turn event log and result store (single process, in memory).

Model
-----
session -- has many --> turn
turn    -- has --> append-only event log (seq 1, 2, 3, ...) + status + result

Rules that fix the "sometimes the frontend hangs / gets the wrong answer" class
of bugs:

* Events are never consumed. A reader keeps a cursor (the SSE Last-Event-ID),
  so streams can drop and re-attach without losing events, and two streams on
  the same turn cannot steal events from each other.
* A turn is terminal once status != "running". finish() is first-wins and
  append_event() refuses to write to a terminal turn, so a late / zombie agent
  thread can neither overwrite a timeout result nor leak events anywhere.
* A stream ends when ITS turn is terminal, not when "the session has a result".
* start_turn() is idempotent per (session, idempotency_key): a retried POST
  gets the same turn_id back instead of starting a second turn.

This module is the only thing that would change if you later move to Redis /
a DB: keep the TurnStore method names and swap the internals.
"""

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# Finished turns (events + result) are kept this long, then swept.
TURN_TTL_SECONDS = float(os.environ.get("TURN_TTL_SECONDS", "3600"))
TERMINAL_STATUSES = frozenset({"done", "failed", "timeout"})


class TurnInProgress(Exception):
    """Raised by start_turn() when the session already has a running turn."""

    def __init__(self, turn_id: str):
        super().__init__(f"turn {turn_id} is still running")
        self.turn_id = turn_id


@dataclass
class _Turn:
    turn_id: str
    session_id: str
    status: str = "running"  # running | done | failed | timeout
    events: list[tuple[int, str]] = field(default_factory=list)  # (seq, payload)
    result: dict | None = None
    finished_at: float | None = None


class TurnStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._turns: dict[str, _Turn] = {}
        self._active: dict[str, str] = {}  # session_id -> running turn_id
        self._latest: dict[str, str] = {}  # session_id -> most recent turn_id
        self._idem: dict[tuple[str, str], str] = {}  # (session_id, key) -> turn_id

    # ------------------------------------------------------------------ write
    def start_turn(
        self, session_id: str, idempotency_key: str | None = None
    ) -> tuple[str, bool]:
        """Return (turn_id, created).

        created=False means this is a replay of an earlier request with the
        same idempotency key: do NOT run the agent again.
        Raises TurnInProgress if a different turn is still running.
        """
        with self._lock:
            self._sweep_locked()
            if idempotency_key:
                known = self._idem.get((session_id, idempotency_key))
                if known in self._turns:
                    return known, False
            active = self._active.get(session_id)
            if active is not None:
                raise TurnInProgress(active)
            turn_id = uuid.uuid4().hex
            self._turns[turn_id] = _Turn(turn_id, session_id)
            self._active[session_id] = turn_id
            self._latest[session_id] = turn_id
            if idempotency_key:
                self._idem[(session_id, idempotency_key)] = turn_id
            return turn_id, True

    def append_event(self, turn_id: str, payload: str) -> int | None:
        """Append to a RUNNING turn. Returns the seq, or None if dropped."""
        with self._lock:
            t = self._turns.get(turn_id)
            if t is None or t.status != "running":
                return None
            seq = len(t.events) + 1
            t.events.append((seq, payload))
            return seq

    def finish(
        self,
        turn_id: str,
        status: str,
        result: dict | None,
        before_commit: Callable[[], None] | None = None,
    ) -> bool:
        """Move a running turn to a terminal status. First caller wins.

        before_commit runs under the store lock, only for the winner, and
        BEFORE the turn becomes terminal / the session becomes free for a new
        turn. Use it to publish the final AgentState (remember_state) so the
        next turn can never load a stale state. If it raises, nothing changes.
        """
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"not a terminal status: {status!r}")
        with self._lock:
            t = self._turns.get(turn_id)
            if t is None or t.status != "running":
                return False
            if before_commit is not None:
                before_commit()
            t.result = result
            t.status = status
            t.finished_at = time.monotonic()
            if self._active.get(t.session_id) == turn_id:
                del self._active[t.session_id]
            return True

    def clear_session(self, session_id: str) -> None:
        """Forget every turn of a session (reset). Zombie threads become no-ops."""
        with self._lock:
            gone = {tid for tid, t in self._turns.items() if t.session_id == session_id}
            for tid in gone:
                del self._turns[tid]
            self._active.pop(session_id, None)
            self._latest.pop(session_id, None)
            self._idem = {k: v for k, v in self._idem.items() if v not in gone}
        logger.info("Cleared turns for session %s", session_id)

    # ------------------------------------------------------------------- read
    def read_events(
        self, turn_id: str, after: int
    ) -> tuple[list[tuple[int, str]], str] | None:
        """Events with seq > after, plus the status read in the same critical
        section. If status is terminal and the list is empty, there is
        provably nothing more to send. None = unknown turn."""
        with self._lock:
            t = self._turns.get(turn_id)
            if t is None:
                return None
            return list(t.events[max(after, 0) :]), t.status

    def get(self, turn_id: str) -> dict | None:
        with self._lock:
            t = self._turns.get(turn_id)
            if t is None:
                return None
            return {
                "turn_id": t.turn_id,
                "session_id": t.session_id,
                "status": t.status,
                "last_event_id": len(t.events),
                "result": dict(t.result) if t.result is not None else None,
            }

    def active_turn(self, session_id: str) -> str | None:
        with self._lock:
            return self._active.get(session_id)

    def latest_turn(self, session_id: str) -> str | None:
        with self._lock:
            tid = self._latest.get(session_id)
            return tid if tid in self._turns else None

    # --------------------------------------------------------------- internal
    def _sweep_locked(self) -> None:
        now = time.monotonic()
        expired = {
            tid
            for tid, t in self._turns.items()
            if t.finished_at is not None and now - t.finished_at > TURN_TTL_SECONDS
        }
        if not expired:
            return
        for tid in expired:
            del self._turns[tid]
        self._idem = {k: v for k, v in self._idem.items() if v not in expired}
        self._latest = {s: t for s, t in self._latest.items() if t not in expired}


store = TurnStore()


# ---------------------------------------------------------------------------
# Publishing from the agent code (signatures kept so callers don't change)
# ---------------------------------------------------------------------------
_current_turn: ContextVar[str | None] = ContextVar("current_turn", default=None)


@contextmanager
def turn_context(turn_id: str):
    """Bind the running turn to this thread/context while the agent executes."""
    token = _current_turn.set(turn_id)
    try:
        yield
    finally:
        _current_turn.reset(token)


def publish_action(session_id: str, tool_name: str) -> None:
    """The tool the reasoner decided to call next."""
    # Prefer the turn bound to this context (immune to zombie threads); fall
    # back to the session's active turn if the context did not propagate
    # (e.g. LangGraph running a node in its own worker thread).
    turn_id = _current_turn.get() or store.active_turn(session_id)
    if turn_id is None:
        return
    payload = json.dumps(
        {"type": "action", "tool": tool_name}, default=str, ensure_ascii=False
    )
    store.append_event(turn_id, payload)


def publish_thought(session_id: str, content: str) -> None:
    """No-op: thoughts are not shown. Delete the callers, then this stub."""
    return None


def clear_session(session_id: str) -> None:
    store.clear_session(session_id)


# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------
def _sse(event: str, data: str, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {data}\n\n"


async def iter_sse(
    turn_id: str,
    after: int = 0,
    poll_interval: float = 0.25,
    keepalive_every: float = 15.0,
):
    """Yield SSE frames for one turn, starting after event id `after`.

    Safe to call many times for the same turn (reconnects, multiple tabs).
    Polling an in-memory list every 250 ms is cheap and, unlike a blocking
    queue.get in a worker thread, is cancelled cleanly on client disconnect.
    """
    cursor = max(after, 0)
    idle = 0.0
    yield "retry: 2000\n\n"
    while True:
        snap = store.read_events(turn_id, cursor)
        if snap is None:  # swept, reset, or never existed
            yield _sse("done", json.dumps({"status": "gone"}))
            return
        events, status = snap
        if events:
            for seq, payload in events:
                cursor = seq
                yield _sse("status", payload, seq)
            idle = 0.0
            continue  # re-read: more events or the terminal state may have landed
        if status != "running":
            yield _sse("done", json.dumps({"status": status}), cursor + 1)
            return
        await asyncio.sleep(poll_interval)
        idle += poll_interval
        if idle >= keepalive_every:
            idle = 0.0
            yield ": keep-alive\n\n"
