from state import AgentState

def interact_simulation(state: AgentState) -> AgentState:
    sim_id = state["simulation_id"]
    state["response"] = f"Interacting with simulation {sim_id}. (Mock reasoning over results)"
    return state
