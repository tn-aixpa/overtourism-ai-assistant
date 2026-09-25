import uuid
import asyncio
import threading
import logging
from typing import Dict, Optional
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# Per-session locks to prevent concurrent mutation
_LOCKS: Dict[str, asyncio.Lock] = {}
_STATE_STORE: Dict[str, AgentState] = {}

# Which sessions currently have a turn actually running in the background
# (see app.api.routes._run_agent). This is deliberately SEPARATE from
# _LOCKS above: the asyncio.Lock in run_agent_endpoint only ever guards the
# brief "load, mutate, save the starting state" step — it is released
# before background_tasks.add_task hands the real work off to a worker
# thread, precisely so the HTTP request can return 202 immediately instead
# of blocking for the full LLM turn. That means nothing previously stopped
# a SECOND /agent call for the same session_id (sent before the first
# turn's background task finishes — a double-submit, a frontend retry
# after a stalled/reconnecting SSE stream, or just a fast second message)
# from being accepted too: it would call load_state(), get back the exact
# same live AgentState OBJECT the first call's background thread is still
# reading/mutating (load_state/save_state store a reference, not a copy),
# and both threads would then race on mutating and eventually
# save_state()-ing (== overwriting the on-disk JSON dump, non-atomically —
# see AgentState.dump_to_file) that one shared object. Whichever thread's
# publish_done() lands second is also silently lost from the requester's
# point of view: the SSE stream already closed after the FIRST "__done__"
# it saw (see stream_events' event_generator), even though the second
# response really was generated (and is sitting, retrievable, in
# get_result — just not streamed).
#
# _IN_FLIGHT (guarded by threading.Lock, not asyncio.Lock: it's read/written
# from the worker thread _run_agent actually runs on, not just from
# coroutines) closes that gap: a second /agent call for a session_id still
# marked in-flight is rejected with 409 instead of silently racing.
_IN_FLIGHT: set[str] = set()
_IN_FLIGHT_LOCK = threading.Lock()


def is_in_flight(session_id: str) -> bool:
    with _IN_FLIGHT_LOCK:
        return session_id in _IN_FLIGHT


def mark_in_flight(session_id: str) -> None:
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT.add(session_id)


def clear_in_flight(session_id: str) -> None:
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT.discard(session_id)


def _get_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session async lock."""
    if session_id not in _LOCKS:
        _LOCKS[session_id] = asyncio.Lock()
    return _LOCKS[session_id]


def load_state(session_id: Optional[str]) -> Optional[AgentState]:
    if not session_id:
        return None
    return _STATE_STORE.get(session_id)


def save_state(state: AgentState) -> None:
    if not state.session_id:
        raise ValueError("AgentState must have a session_id before saving")
    _STATE_STORE[state.session_id] = state
    logger.debug(f"State saved for session {state.session_id}")

    state.dump_to_file(f"logs/state_{state.session_id}.json")


def delete_state(session_id: str) -> None:
    """Clean up state and lock when a session ends."""
    _STATE_STORE.pop(session_id, None)
    _LOCKS.pop(session_id, None)
    clear_in_flight(session_id)
