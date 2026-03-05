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

    # For debugging, replace later with proper saving
    with open("logs/traceback.log", "w") as f:
        f.write(f"Saved state for session_id={key}, last node={state.last_node}\n")
        for trace in state.cognitive.trace.steps:
            f.write(f"  - {trace.timestamp} | {trace.step_type} | {trace.node} | {str(trace.data)}\n")