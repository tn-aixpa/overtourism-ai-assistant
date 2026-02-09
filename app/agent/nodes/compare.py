from ..state import AgentState
from ...utils.llm import answer_question_comparison

def compare_scenarios(state: AgentState) -> AgentState:
    # check state
    if len(state.scenario_ids) < 2:
        state.response = f"Something went wrong. Number of active scenarios: {len(state.scenario_ids)}."
        return state
    

    # load data if needed
    unavailable = [sim for sim in state.scenario_ids if sim not in state.data]
    if len(unavailable):
        # TODO: implement fallback to try to load data
        state.response = f"Scenario data for id {unavailable} is not available right now. Please try again later."
        return state

    state.expert_answers = {}

    # answer user question
    for role in state.selected_roles:

        answer = answer_question_comparison(
            question=state.messages[-1]["content"] if state.messages else "",
            data=state.data,
            role=role,
        )
        state.expert_answers[role] = answer
    
    if len(state.selected_roles) == 1:
        state.response = next(iter(state.expert_answers.values()))

    return state