from ..state import AgentState

def error_recovery_node(state: AgentState, error_message: str = None) -> AgentState:
    """
    Catch errors from previous nodes, log them, and provide a safe response.
    """
    if error_message:
        print(f"[ERROR] {error_message}")  # Logging for debug/tracing

    # Reset critical flags to avoid unsafe operations
    state.running_simulation = False
    state.awaiting_confirmation = False
    state.next_action = None

    # Provide user-friendly fallback
    state.response = (
        "Oops! Something went wrong while processing your request. "
        "Please check your inputs or try again."
    )
    return state
