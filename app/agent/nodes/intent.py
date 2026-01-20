from ..state import AgentState
from ...utils.llm import classify_intent

def intent_node(state: AgentState) -> AgentState:

    answer = classify_intent(state.sim_ids, state.user_message)
    if "Error" not in answer:  
      state.next_action = answer
    else:
      #TODO: impement
      pass
    return state
