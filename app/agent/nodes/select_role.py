from ..state import AgentState
from ...config import ALLOWED_ROLES
from ...utils.llm import select_role_llm

def select_role(state: AgentState) -> AgentState:
    question = state.user_message
    raw = select_role_llm(question, ALLOWED_ROLES)

    if "Error" in raw:
        #TODO: handle this
        roles = ["Data Analyst"]
        return state
    
    # ---- Parse & normalize ----
    roles = []
    for r in raw.split(","):
        key = r.strip()
        roles.append(key)
    
    state.selected_roles = roles

    return state
