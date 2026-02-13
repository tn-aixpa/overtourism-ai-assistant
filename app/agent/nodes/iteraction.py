from ..state import AgentState
from ...config import ALLOWED_ROLES
from ...utils.llm import select_role_llm, answer_question, answer_question_comparison, synthesize_llm

def select_role(state: AgentState) -> AgentState:
    question = state.messages[-1]["content"] if state.messages else ""
    raw = select_role_llm(question, ALLOWED_ROLES)

    if "Error" in raw:
        roles = ["Data Analyst"]
        return state
    
    # ---- Parse & normalize ----
    roles = []
    for r in raw.split(","):
        key = r.strip()
        roles.append(key)

    if not roles:
        roles = ["Data Analyst"]
    
    state.selected_roles = roles

    return state

def interact_scenario(state: AgentState) -> AgentState:

    # check state
    if len(state.scenario_ids) == 0:
        state.messages.append({"role": "assistant", "content": "Something went wrong. No scenario is available to interact with."})
        return state
    
    if len(state.scenario_ids) > 1:
        state.messages.append({"role": "assistant", "content": "Something went wrong. More than one active scenario found."})
        return state
    

    # load data if needed
    if state.scenario_ids[0] not in state.data:
        state.messages.append({"role": "assistant", "content": f"Scenario data for id {state.scenario_ids[0]} is not available right now. Please try again later."})
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
        state.messages.append({"role": "assistant", "content": next(iter(state.expert_answers.values()))})

    return state

def compare_scenarios(state: AgentState) -> AgentState:
    # check state
    if len(state.scenario_ids) < 2:
        state.messages.append({"role": "assistant", "content": f"Something went wrong. Number of active scenarios: {len(state.scenario_ids)}. Please ensure at least two scenarios are active."})
        return state
    

    # load data if needed
    unavailable = [sim for sim in state.scenario_ids if sim not in state.data]
    if len(unavailable):
        state.messages.append({"role": "assistant", "content": f"Scenario data for id {unavailable} is not available right now. Please try again later."})
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
        state.messages.append({"role": "assistant", "content": next(iter(state.expert_answers.values()))})

    return state


def synthesize_answers(state: AgentState) -> AgentState:
    # Safety check
    assert len(state.expert_answers) > 1
    
    answer = synthesize_llm(state.messages[-1]["content"] if state.messages else "",
                            state.expert_answers)

    assert not answer.startswith("Error")

    state.messages.append({
        "role": "assistant",
        "content": answer
    })

    return state
