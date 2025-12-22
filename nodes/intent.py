from utils.llm import classify_intent
from state import AgentState

def intent_node(state: AgentState) -> AgentState:
    prompt = f"""
User request: {state['user_message']}

Current state:
- simulation_id: {state['simulation_id']}
- sim1: {state['sim1']}
- sim2: {state['sim2']}
- running_simulation: {state['running_simulation']}

Choose one action:
INTERACT_SIMULATION
COMPARE_SIMULATIONS
RUN_NEW_SIMULATION
ASK_CLARIFICATION

Return only the action name.
"""
    state["next_action"] = classify_intent(prompt)
    return state
