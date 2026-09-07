"""
SSE event bus used to stream agent progress to the front-end while a request
is being processed in the background.

Each session has:
- a persistent event queue used by the SSE endpoint;
- a final result stored separately so the client can reliably retrieve the
  completed answer even if the SSE connection is interrupted or established
  after the agent has already finished.

The final result is deliberately NOT consumed by get_result(). This makes the
result endpoint idempotent and allows the frontend to retry after transient
network/proxy failures such as ERR_INCOMPLETE_CHUNKED_ENCODING.
"""

import json
import logging
import threading
from queue import Queue
from collections import defaultdict

logger = logging.getLogger(__name__)

# One queue per session. Queues are created lazily and remain available until
# clear_session() is called.
_queues: dict[str, Queue] = defaultdict(Queue)

# Final results are stored separately from SSE events. Access is protected by
# a lock because the agent runs in a worker thread while HTTP handlers may
# read the result concurrently.
_results: dict[str, dict] = {}
_results_lock = threading.RLock()


def get_queue(session_id: str) -> Queue:
    """Return the persistent SSE queue for a session."""
    return _queues[session_id]


def publish(session_id: str, event: str) -> None:
    """Push a raw string onto the session's SSE queue."""
    logger.info("Publishing event to session %s: %s", session_id, event)
    _queues[session_id].put(event)


def _publish_json(session_id: str, payload: dict) -> None:
    publish(
        session_id,
        json.dumps(payload, default=str, ensure_ascii=False),
    )


def publish_thought(session_id: str, content: str) -> None:
    """A reasoning step in the ReAct loop, before an action is decided."""
    _publish_json(
        session_id,
        {"type": "thought", "content": content},
    )


def publish_action(session_id: str, tool_name: str) -> None:
    """The tool the reasoner decided to call next."""
    _publish_json(
        session_id,
        {"type": "action", "tool": tool_name},
    )


def publish_done(session_id: str, result: dict) -> None:
    """
    Store the final result BEFORE signalling completion on SSE.

    The ordering is intentional: once the frontend observes `__done__`, the
    result must already be available through get_result().
    """
    with _results_lock:
        _results[session_id] = result

    logger.info("Agent completed session %s", session_id)

    # Signal completion after storing the result. A stream that is already
    # connected receives this event; a stream that connects later can still
    # obtain the final answer through get_result().
    _queues[session_id].put("__done__")


def get_result(session_id: str) -> dict | None:
    """
    Return the final result without consuming it.

    This is intentionally idempotent so a frontend can retry the request
    after a failed SSE connection or transient network error.
    """
    with _results_lock:
        result = _results.get(session_id)
        if result is None:
            return None

        # Return a shallow copy so callers cannot accidentally replace the
        # stored result object.
        return dict(result)


def clear_session(session_id: str) -> None:
    """
    Drop all queued events and the stored result for a session.

    Called on session reset so a stale stream from a previous conversation
    cannot leak into a new one.
    """
    _queues.pop(session_id, None)

    with _results_lock:
        _results.pop(session_id, None)

    logger.info("Cleared event state for session %s", session_id)
