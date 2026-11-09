import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# Per-session locks to prevent concurrent mutation
_LOCKS: Dict[str, asyncio.Lock] = {}
_STATE_STORE: Dict[str, AgentState] = {}

# Guards the two operations that touch page_context across threads: the
# /agent/context update (event-loop thread) and a finishing turn replacing the
# stored state (pool thread, remember_state). Held for microseconds, no I/O.
_STATE_MUTEX = threading.Lock()

# NOTE: "is a turn already running for this session?" is NOT tracked here.
# That is owned by app.agent.events.TurnStore (start_turn() raises
# TurnInProgress -> 409), which releases the session atomically in finish().
# _LOCKS above only guards the brief "load, mutate, save the starting state"
# step in run_agent_endpoint.


def _get_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session async lock."""
    if session_id not in _LOCKS:
        _LOCKS[session_id] = asyncio.Lock()
    return _LOCKS[session_id]


def load_state(session_id: Optional[str]) -> Optional[AgentState]:
    if not session_id:
        return None
    return _STATE_STORE.get(session_id)


def remember_state(state: AgentState) -> None:
    """In-memory only (microseconds): what the next request's load_state() sees."""
    if not state.session_id:
        raise ValueError("AgentState must have a session_id before saving")
    with _STATE_MUTEX:
        stored = _STATE_STORE.get(state.session_id)
        # A turn works on its own copy of the state. If a newer page snapshot
        # was stored while it ran (POST /agent/context), keep that one: the
        # turn never saw it, and the commit must not roll it back.
        if (
            stored is not None
            and stored is not state
            and stored.page_context_version > state.page_context_version
        ):
            state.page_context = stored.page_context
            state.page_context_version = stored.page_context_version
        _STATE_STORE[state.session_id] = state


def persist_state(state: AgentState) -> None:
    """Slow disk dump (debug/audit copy). Never call on the event loop or before the turn is finished (store.finish)."""
    state.dump_to_file(f"logs/state_{state.session_id}.json")


def save_state(state: AgentState) -> None:
    remember_state(state)
    persist_state(state)


def delete_state(session_id: str) -> None:
    """Clean up state and lock when a session ends."""
    _STATE_STORE.pop(session_id, None)
    _LOCKS.pop(session_id, None)


@dataclass
class PageContextUpdate:
    applied: bool
    version: int  # server-side count of accepted snapshots
    revision: Optional[int]  # client revision of the snapshot now stored
    state: AgentState  # the stored object that was updated


def set_page_context(
    session_id: str, page_context: Dict[str, Any]
) -> Optional[PageContextUpdate]:
    """Replace ONLY the page snapshot of the stored state (None if the session
    is gone). A snapshot whose client `revision` is not newer than the stored
    one is stale (out-of-order or retried request) and is not applied. Without
    a revision on either side, the last write wins."""
    with _STATE_MUTEX:
        state = _STATE_STORE.get(session_id)
        if state is None:
            return None
        current = (state.page_context or {}).get("revision")
        new = page_context.get("revision")
        if current is not None and new is not None and new <= current:
            return PageContextUpdate(False, state.page_context_version, current, state)
        state.page_context = page_context
        state.page_context_version += 1
        return PageContextUpdate(True, state.page_context_version, new, state)
