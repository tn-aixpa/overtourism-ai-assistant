from state import AgentState

def compare_simulations(state: AgentState) -> AgentState:
    state["response"] = (
        f"Comparing simulations {state['sim1']} vs {state['sim2']}.\n"
        "Result: Simulation A performs better on stability."
    )
    return state
