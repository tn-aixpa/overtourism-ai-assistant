from ..state import AgentState
from ...utils.llm import synthesize_llm

def synthesize_answers(state: AgentState) -> AgentState:
    # Safety check
    if len(state.expert_answers) <= 1:
        # TODO: handle this
        return state
    
    answer = synthesize_llm(state.user_message, state.expert_answers)

    if "Error" in answer:
        #TODO: handle this
        pass

    state.response = answer

    return state
