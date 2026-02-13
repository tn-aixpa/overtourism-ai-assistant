from langgraph.graph import END
from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import classify_intent

def intent_node(state: AgentState) -> AgentState:
    answer = classify_intent(state.scenario_ids, state.messages[-1]["content"] if state.messages else "").strip()

    VALID_OUTPUTS = {
        "CREATE_PROBLEM",
        "RUN_NEW_SCENARIO",
        "INTERACT_SCENARIO",
        "INVALID",
    }

    assert answer in VALID_OUTPUTS
    state.next_action = answer
    return state

def validate_intent_node(state: AgentState) -> AgentState:
    """
    Validate the intent determined in the intent_node.
    Adjust the next_action and response if needed based on the current state.
    """
    intent = state.next_action

    # --- INVALID intent ---
    if intent == "INVALID":
        state.next_action = "INVALID"
        state.messages.append({
            "role": "assistant",
            "content": "I'm not able to handle this request with the current system capabilities."
        })
        return state

    # --- INTERACT_SCENARIO ---
    if intent == "INTERACT_SCENARIO":
        if not state.scenario_ids:
            state.next_action = "NOT_ALLOWED"
            state.messages.append({
                "role": "assistant",
                "content": "I understand you want to interact with a scenario, but no scenario is currently selected."
            })
            return state

        if len(state.scenario_ids) > 1:
            state.next_action = "COMPARE_SCENARIOS"
            return state
        
    # --- CREATE_PROBLEM ---
    if intent == "RUN_NEW_SCENARIO" and not state.problem_id:
        state.next_action = "NOT_ALLOWED"
        state.messages.append({
            "role": "assistant",
            "content": "No problem is defined. Please define a problem first."
        })
        return state

    # --- RUN_NEW_SCENARIO ---
    if intent == "RUN_NEW_SCENARIO" and state.running_scenario:
        state.next_action = "NOT_ALLOWED"
        state.messages.append({
            "role": "assistant",
            "content": "A scenario is already running. Please wait for it to finish before starting a new one."
        })
        return state
    


    return state

def route_from_intent(state: AgentState):
    action = state.next_action
    if action in ["INTERACT_SCENARIO", "COMPARE_SCENARIOS"]:
        return Command(update=state, goto="interaction", graph=Command.PARENT)

    # Scenario runner subgraph

    if action == "RUN_NEW_SCENARIO":
        return Command(update=state, goto="scenario_extraction", graph=Command.PARENT)

    if action == "CREATE_PROBLEM":
        return Command(update=state, goto="problem", graph=Command.PARENT)

    # END nodes
    if action in ["NOT_ALLOWED", "INVALID"]:
        return Command(update=state, goto=END)
    

    # Fallback safety
    return Command(update=state, goto="error", graph=Command.PARENT)