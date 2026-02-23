import uuid
from typing import Dict
from app.agent.state import AgentState

# In-memory store
_STATE_STORE: Dict[str, AgentState] = {}


def generate_key() -> str:
    """Generate a random conversation key."""
    return str(uuid.uuid4())


def load_state(key: str | None) -> tuple[str, AgentState]:
    """
    Load existing state by key.
    If key is None or not found, create a new state with a new key.
    Returns (key, state).
    """
    if key and key in _STATE_STORE:
        return key, _STATE_STORE[key]

    new_key = generate_key()
    state = AgentState(session_id=new_key)
    _STATE_STORE[new_key] = state
    return new_key, state


def save_state(key: str, state: AgentState) -> None:
    _STATE_STORE[key] = state