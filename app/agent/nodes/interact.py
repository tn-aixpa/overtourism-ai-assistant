from ..state import AgentState
from ...utils.llm import answer_question

def interact_simulation(state: AgentState) -> AgentState:

    # check state
    if len(state.sim_ids) == 0:
        state.response = "Something went wrong. No simulation is available to interact with."
        return state
    
    if len(state.sim_ids) > 1:
        state.response = "Something went wrong. More than one active simulation"
        return state
    

    # load data if needed
    if state.sim_ids[0] not in state.simulation_data:
        # TODO: implement fallback to try to load data
        state.response = f"Simulation data for id {state.sim_ids[0]} is not available right now. Please try again later."
        return state

    state.expert_answers = {}

    # answer user question
    for role in state.selected_roles:

        answer = answer_question(
            question=state.user_message,
            data=state.simulation_data,
            role=role,
        )
        state.expert_answers[role] = answer
    
    if len(state.selected_roles) == 1:
        state.response = next(iter(state.expert_answers.values()))

    return state
