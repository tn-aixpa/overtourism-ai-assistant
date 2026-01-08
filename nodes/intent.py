from utils.llm import classify_intent
from state import AgentState

def intent_node(state: AgentState) -> AgentState:
    active_sims = [s for s in [state["sim1_id"], state["sim2_id"]] if s]

    prompt = f"""
You are an intent classifier.
Your task is to determine the user's intended action.

Possible actions:
- INTERACT_SIMULATION: Analyze, explain, interpret, or explore existing simulations.
- RUN_NEW_SIMULATION: Create, run, start, or re-run a simulation, including modifying
  parameters of an existing simulation.
- INVALID: The request is totally unclear and the intent cannot be determined or the request is clear but unrelated to simulations or system capabilities.

Decision rules:

1. If the user request is clear and refers to a simulation → INTERACT_SIMULATION.
3. If the user request asks to run, create, start, or modify a simulation → RUN_NEW_SIMULATION.
4. If the request is unrelated to simulations → INVALID.
5. If the request is totally unclear or vague → INVALID.

Context: overtourism in New York.
The Context provides background but does not override the intent rules.

User request: {state['user_message']}
Active simulations: {active_sims or "none"}

Return only the action name.

"""
       
    state["next_action"] = classify_intent(prompt)
    return state
