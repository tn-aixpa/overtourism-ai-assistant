"""
SSE event bus used to stream agent progress to the front-end while a request
is being processed in the background.

Design (turn-scoped, append-only, multi-reader-safe)
-----------------------------------------------------
Each session holds an append-only list of events for its CURRENT turn, plus
the turn's stored final result. A reader asks for "everything since index
N" and gets back a slice — it never consumes/removes anything.

This replaces an earlier design built on a single shared Queue per session,
where reading meant Queue.get() — i.e. consuming. That broke in production:
when an SSE connection was abandoned (a proxy in front of it cut the
connection, the tab reconnected, whatever), the coroutine serving it went
away, but the WORKER THREAD blocked inside Queue.get() did not — it kept
waiting, and whichever event arrived next (confirmed via logs: usually
"__done__" itself) was handed to that dead thread and silently discarded,
while the actually-live stream — or the reconnect that replaced it — never
saw it. Two live consumers had the same problem in reverse: they'd split a
single turn's events between them, each missing whatever the other one
happened to .get() first.

With an append-only log + a `since` offset instead, any number of readers —
a fresh connection, a reconnect after a voluntary rotation (see
app.api.routes.stream_events) or an involuntary one (a proxy timeout we
didn't manage to preempt), or several browser tabs on the same session —
can each independently read every event from wherever THEY left off, and
none of them can take an event away from another reader. Nothing is ever
truly "consumed" except by start_turn() moving on to the next turn.
"""

import json
import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)


class _SessionLog:
    __slots__ = ("events", "result", "condition")

    def __init__(self) -> None:
        self.events: list[str] = []
        self.result: dict | None = None
        # A threading.Condition, not an asyncio primitive: publishers run
        # in the agent's worker thread (see app.api.routes._run_agent) and
        # readers block via asyncio.to_thread (see stream_events), so both
        # sides need a primitive usable from plain OS threads.
        self.condition = threading.Condition()


# One log per session, created lazily. Access to the dict itself (adding a
# new session) is protected separately from each session's own state (which
# is protected by that session's own condition's lock) so that one busy
# session's readers/writers never block another session from being looked
# up or created.
_sessions: dict[str, _SessionLog] = defaultdict(_SessionLog)
_sessions_lock = threading.Lock()


def _get_log(session_id: str) -> _SessionLog:
    with _sessions_lock:
        return _sessions[session_id]


def start_turn(session_id: str) -> None:
    """Reset a session's event log and stored result for a NEW turn.

    Must be called once per turn, before the background agent run starts
    (see app.api.routes.run_agent_endpoint) — a session's log is otherwise
    cumulative across every turn it's ever had, which would mean: (1) a
    stream connecting fresh (since=0) for turn 5 would replay every event
    from turns 1-4 before reaching anything relevant, and (2) get_result()
    would keep returning turn 4's answer for the whole time turn 5 is
    still running, since nothing had told it turn 4 was no longer current.
    """
    log = _get_log(session_id)
    with log.condition:
        log.events = []
        log.result = None
        log.condition.notify_all()


def _append(session_id: str, event: str) -> None:
    log = _get_log(session_id)
    with log.condition:
        log.events.append(event)
        log.condition.notify_all()
    logger.info("Publishing event to session %s: %s", session_id, event)


def _publish_json(session_id: str, payload: dict) -> None:
    _append(session_id, json.dumps(payload, default=str, ensure_ascii=False))


def publish_thought(session_id: str, content: str) -> None:
    """A reasoning step in the ReAct loop, before an action is decided."""
    _publish_json(session_id, {"type": "thought", "content": content})


def publish_action(session_id: str, tool_name: str) -> None:
    """The tool the reasoner decided to call next."""
    _publish_json(session_id, {"type": "action", "tool": tool_name})


def publish_done(session_id: str, result: dict) -> None:
    """
    Store the final result BEFORE appending the completion marker.

    The ordering is intentional: once a reader observes "__done__" in the
    event list, the result must already be available through get_result() —
    both happen under the same lock here, so there is no window where a
    reader could see one without the other.
    """
    log = _get_log(session_id)
    with log.condition:
        log.result = result
        log.events.append("__done__")
        log.condition.notify_all()

    logger.info("Agent completed session %s", session_id)


def get_events_since(
    session_id: str, since: int, timeout: float
) -> tuple[list[str], int]:
    """
    Block up to `timeout` seconds for events beyond index `since`, then
    return (new_events, new_since) — pass `new_since` back in as `since` on
    the next call to avoid re-reading anything already returned.

    Returns ([], since) unchanged on a plain timeout — the caller (see
    stream_events) treats that as "nothing new yet", e.g. by sending an SSE
    keep-alive comment and calling again. This never removes anything from
    the log, so the exact same range can be read again by this call, a
    concurrent one, or a later reconnect (see the module docstring).
    """
    log = _get_log(session_id)
    with log.condition:
        got = log.condition.wait_for(lambda: len(log.events) > since, timeout=timeout)
        if not got:
            return [], since
        new_events = log.events[since:]
        return new_events, since + len(new_events)


def get_result(session_id: str) -> dict | None:
    """
    Return the final result for the CURRENT turn without consuming it.

    Intentionally idempotent so a frontend can retry after a failed SSE
    connection or transient network error. Returns None if the current
    turn (i.e. since the last start_turn() call) hasn't finished yet — in
    particular, this is what stops a caller from ever seeing a PREVIOUS
    turn's answer while a new one is still in progress, since start_turn()
    clears it up front rather than leaving the old value in place until
    overwritten.
    """
    log = _get_log(session_id)
    with log.condition:
        if log.result is None:
            return None
        # Shallow copy so callers cannot accidentally mutate the stored
        # result object.
        return dict(log.result)


def clear_session(session_id: str) -> None:
    """
    Drop ALL state for a session (not just the current turn's).

    Called on session reset so a stale stream/result from a previous
    conversation cannot leak into a new one.
    """
    with _sessions_lock:
        log = _sessions.pop(session_id, None)
    if log is not None:
        with log.condition:
            # Wake up anything still blocked in get_events_since for this
            # session (e.g. a stream whose client just hit reset) so it can
            # notice the session is gone rather than sitting on its full
            # timeout — get_events_since itself will simply see an empty,
            # freshly-recreated log on its next call (a new defaultdict
            # entry) if anyone still queries this session_id afterwards.
            log.condition.notify_all()
    logger.info("Cleared event state for session %s", session_id)
