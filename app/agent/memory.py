from typing import Dict, NamedTuple

from .state import AgentState


class ConversationKey(NamedTuple):
    session_id: str
    problem_id: str
    scenario_ids: tuple[str, ...]
    
_STATE_STORE: Dict[ConversationKey, AgentState] = {}

def make_key(
    session_id: str,
    problem_id: str | None,
    scenario_ids: list[str] | None,
) -> ConversationKey:
    return ConversationKey(
        session_id=session_id,
        problem_id=problem_id or "",
        scenario_ids=tuple(sorted(scenario_ids)) if scenario_ids else (),
    )

def load_state(key: ConversationKey) -> AgentState:
    return _STATE_STORE.get(
        key,
        AgentState(
            session_id=key.session_id,
            problem_id=key.problem_id,
            scenario_ids=list(key.scenario_ids),
        ),
    )

def save_state(key: ConversationKey, state: AgentState):
    _STATE_STORE[key] = state
