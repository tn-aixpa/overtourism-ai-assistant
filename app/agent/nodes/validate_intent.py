from ..state import AgentState

def validate_intent_node(state: AgentState) -> AgentState:
    """
    Validate the intent determined in the intent_node.
    Adjust the next_action and response if needed based on the current state.
    """
    intent = state.next_action

    # --- INVALID intent ---
    if intent == "INVALID":
        state.next_action = "INVALID"
        state.response = (
            "I'm not able to handle this request with the current system capabilities."
        )
        return state

    # --- INTERACT_SCENARIO ---
    if intent == "INTERACT_SCENARIO":
        if not state.scenario_ids:
            state.next_action = "NOT_ALLOWED"
            state.response = (
                "I understand you want to interact with a scenario, "
                "but no scenario is currently selected."
            )
            return state

        if len(state.scenario_ids) > 1:
            state.next_action = "COMPARE_SCENARIOS"
            return state

    # --- RUN_NEW_SCENARIO ---
    if intent == "RUN_NEW_SCENARIO" and state.running_scenario:
        state.next_action = "NOT_ALLOWED"
        state.response = (
            "A scenario is already running. Please wait for it to finish "
            "before starting a new one."
        )
        return state

    return state
