import uuid
import asyncio
import logging
from typing import Dict, Optional
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# Per-session locks to prevent concurrent mutation
_LOCKS: Dict[str, asyncio.Lock] = {}
_STATE_STORE: Dict[str, AgentState] = {}


def generate_key() -> str:
    return str(uuid.uuid4())


def _get_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session async lock."""
    if session_id not in _LOCKS:
        _LOCKS[session_id] = asyncio.Lock()
    return _LOCKS[session_id]


def load_state(session_id: Optional[str]) -> Optional[AgentState]:
    if not session_id:
        return None
    return _STATE_STORE.get(session_id)

def _save_conversation(state: AgentState):
    state.save()
    state.dump_to_file(f"logs/state_{state.session_id}.json")

def save_state(state: AgentState) -> None:
    if not state.session_id:
        raise ValueError("AgentState must have a session_id before saving")
    _STATE_STORE[state.session_id] = state
    logger.debug(f"State saved for session {state.session_id}")

    _save_conversation(state)


def delete_state(session_id: str) -> None:
    """Clean up state and lock when a session ends."""
    _STATE_STORE.pop(session_id, None)
    _LOCKS.pop(session_id, None)