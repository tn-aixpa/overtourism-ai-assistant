from ..state import AgentState

def compare_simulations(state: AgentState) -> AgentState:
    state.response = (
        f"Comparing simulations {state.sim1_id} vs {state.sim2_id}.\n"
        "Result: Simulation A performs better on stability."
    )
    return state
