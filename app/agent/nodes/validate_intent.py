from ..state import AgentState

def validate_intent_node(state: AgentState) -> AgentState:
    """
    Validate the intent determined in the intent_node.
    Adjust the next_action and response if needed based on the current state.
    """
    intent = state.next_action
    active = state.get_active_simulations()

    # --- INVALID intent ---
    if intent == "INVALID":
        state.next_action = "INVALID"
        state.response = (
            "I'm not able to handle this request with the current system capabilities."
        )
        return state

    # --- INTERACT_SIMULATION ---
    if intent == "INTERACT_SIMULATION":
        if not active:
            state.next_action = "NOT_ALLOWED"
            state.response = (
                "I understand you want to interact with a simulation, "
                "but no simulation is currently selected."
            )
            return state

        if len(active) > 1:
            state.next_action = "COMPARE_SIMULATIONS"
            return state

    # --- RUN_NEW_SIMULATION ---
    if intent == "RUN_NEW_SIMULATION" and state.running_simulation:
        state.next_action = "NOT_ALLOWED"
        state.response = (
            "A simulation is already running. Please wait for it to finish "
            "before starting a new one."
        )
        return state

    return state
