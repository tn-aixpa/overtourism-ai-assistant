import uuid
from typing import Dict, Optional
from app.agent.state import AgentState

# In-memory store
_STATE_STORE: Dict[str, AgentState] = {}


def generate_key() -> str:
    """Generate a random conversation key."""
    return str(uuid.uuid4())


def load_state(session_id: Optional[str]) -> Optional[AgentState]:
    """
    Retrieve AgentState from memory.
    Returns None if not found.
    """
    if not session_id:
        return None

    return _STATE_STORE.get(session_id)


def save_state(key: str, state: AgentState) -> None:
    _STATE_STORE[key] = state

    #state.save()
    #state.dump_to_file(f"logs/state_{state.session_id}.json")