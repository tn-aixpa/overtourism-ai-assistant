import asyncio
import logging
from typing import Dict, Optional
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# Per-session locks to prevent concurrent mutation
_LOCKS: Dict[str, asyncio.Lock] = {}
_STATE_STORE: Dict[str, AgentState] = {}

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
