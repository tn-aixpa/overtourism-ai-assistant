from ..state import AgentState
from ...utils.llm import answer_question

def interact_scenario(state: AgentState) -> AgentState:

    # check state
    if len(state.scenario_ids) == 0:
        state.response = "Something went wrong. No scenario is available to interact with."
        return state
    
    if len(state.scenario_ids) > 1:
        state.response = "Something went wrong. More than one active scenario found."
        return state
    

    # load data if needed
    if state.scenario_ids[0] not in state.data:
        # TODO: implement fallback to try to load data
        state.response = f"Scenario data for id {state.scenario_ids[0]} is not available right now. Please try again later."
        return state

    state.expert_answers = {}

    # answer user question
    for role in state.selected_roles:

        answer = answer_question(
            question=state.messages[-1]["content"] if state.messages else "",
            data=state.data,
            role=role,
        )
        state.expert_answers[role] = answer
    
    if len(state.selected_roles) == 1:
        state.response = next(iter(state.expert_answers.values()))

    return state
