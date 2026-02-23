from datetime import datetime
from ..state import AgentState, ConversationMessage
from ...config import ALLOWED_ROLES
from ...utils.llm import select_role_llm, answer_question, answer_question_comparison, synthesize_llm

def select_role(state: AgentState) -> AgentState:
    question = state.last_user_en
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
    
    state.cognitive.selected_roles = roles

    return state

def interact_scenario(state: AgentState) -> AgentState:

    # check state
    if len(state.cognitive.scenario_ids) == 0:
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content="Something went wrong. No scenario is available to interact with.",
                timestamp=datetime.now()
        ))
    
    if len(state.cognitive.scenario_ids) > 1:
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content="Something went wrong. More than one active scenario found.",
                timestamp=datetime.now()
        ))
        return state
    

    # load data if needed
    if state.cognitive.scenario_ids[0] not in state.cognitive.data:
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content=f"Scenario data for id {state.cognitive.scenario_ids[0]} is not available right now. Please try again later.",
                timestamp=datetime.now()
        ))        
        return state

    state.cognitive.expert_answers = {}

    # answer user question
    for role in state.cognitive.selected_roles:

        answer = answer_question(
            question=state.last_user_en,
            data=state.cognitive.data,
            role=role,
        )
        state.cognitive.expert_answers[role] = answer
    
    if len(state.cognitive.selected_roles) == 1:
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content=next(iter(state.cognitive.expert_answers.values())),
                timestamp=datetime.now()
        ))

    return state

def compare_scenarios(state: AgentState) -> AgentState:
    # check state
    if len(state.cognitive.scenario_ids) < 2:
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content=f"Something went wrong. Number of active scenarios: {len(state.cognitive.scenario_ids)}. Please ensure at least two scenarios are active.",
                timestamp=datetime.now()
        ))
        return state
    

    # load data if needed
    unavailable = [sim for sim in state.cognitive.scenario_ids if sim not in state.cognitive.data]
    if len(unavailable):
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content=f"Scenario data for id {unavailable} is not available right now. Please try again later.",
                timestamp=datetime.now()
        ))
        
        return state

    state.cognitive.expert_answers = {}

    # answer user question
    for role in state.cognitive.selected_roles:

        answer = answer_question_comparison(
            question=state.last_user_en,
            data=state.cognitive.data,
            role=role,
        )
        state.cognitive.expert_answers[role] = answer
    
    if len(state.cognitive.selected_roles) == 1:
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content=next(iter(state.cognitive.expert_answers.values())),
                timestamp=datetime.now()
        ))
        
    return state


def synthesize_answers(state: AgentState) -> AgentState:
    # Safety check
    assert len(state.cognitive.expert_answers) > 1
    
    answer = synthesize_llm(state.last_user_en,
                            state.cognitive.expert_answers)

    assert not answer.startswith("Error")

    state.conversation.append(
        ConversationMessage(
            role="assistant",
            content=answer,
            timestamp=datetime.now()
    ))

    return state
