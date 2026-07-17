"""
SSE event bus used to stream the agent's ReAct reasoning to the front-end
while a request is being processed in the background.

Each session gets its own Queue. `_run_agent` (in api/routes.py) runs the
graph in a worker thread and calls the `publish_*` helpers below as the
ReAct loop progresses; `GET /agent/stream/{session_id}` drains the queue as
Server-Sent Events. The final result is stashed separately via
`publish_done` / `get_result` so the client can also poll for it.

Event payloads are JSON strings with a "type" discriminator so the
front-end can render each stage of the loop distinctly:

    {"type": "thought",     "content": "..."}
    {"type": "action",      "tool": "...", "arguments": {...}}
    {"type": "observation", "tool": "...", "result": {...}}
    {"type": "waiting",     "message": "..."}
    {"type": "final",       "message": "..."}
"""

import json
from queue import Queue
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

_queues: dict[str, Queue] = defaultdict(Queue)
_results: dict[str, dict] = {}  # store final results here


def get_queue(session_id: str) -> Queue:
    return _queues[session_id]


def publish(session_id: str, event: str):
    """Low-level publish: pushes a raw string onto the session's SSE queue."""
    logger.info(f"Publishing event to session {session_id}: {event}")
    _queues[session_id].put(event)


def _publish_json(session_id: str, payload: dict):
    publish(session_id, json.dumps(payload, default=str, ensure_ascii=False))


def publish_thought(session_id: str, content: str) -> None:
    """A reasoning step in the ReAct loop, before an action is decided."""
    _publish_json(session_id, {"type": "thought", "content": content})


def publish_action(session_id: str, tool_name: str) -> None:
    """The tool the reasoner decided to call next."""
    _publish_json(
        session_id,
        {"type": "action", "tool": tool_name},
    )


def publish_done(session_id: str, result: dict):
    _results[session_id] = result  # store before signalling done
    _queues[session_id].put("__done__")


def get_result(session_id: str) -> dict | None:
    return _results.pop(session_id, None)


def clear_session(session_id: str) -> None:
    """Drop any queued events / stored result for a session. Called on
    session reset so a stale stream from a previous conversation never
    leaks into a new one."""
    _queues.pop(session_id, None)
    _results.pop(session_id, None)
