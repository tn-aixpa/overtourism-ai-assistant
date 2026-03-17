import logging

from ..state import AgentState
from ...config import ALLOWED_ROLES
from ...utils.llm import select_role_llm, answer_question, answer_question_comparison, synthesize_llm
from ...utils.error_codes import ErrorCode, GraphError
from ...utils.common import translate_from_eng

logger = logging.getLogger(__name__)

def select_role(state: AgentState) -> AgentState:
    question = state.get_last_user_message().content_en
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

    logger.info(f"Selected roles: {roles}")

    return state

def interact_scenario(state: AgentState) -> AgentState:

    # check state
    if len(state.cognitive.scenario_ids) == 0:
        logger.error("No active scenario")
        raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "No active scenario")       
    
    if len(state.cognitive.scenario_ids) > 1:
        logger.error("Multiple active scenarios")
        raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "Select a single scenario")  
    

    # load data if needed
    if state.cognitive.scenario_ids[0] not in state.cognitive.data:
        logger.error("Data for selected scenario unavailable")
        raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "Data for selected scenario unavailable")  

    state.cognitive.expert_answers = {}

    # answer user question
    for role in state.cognitive.selected_roles:

        answer = answer_question(
            question=state.get_last_user_message().content_en,
            data=state.cognitive.data,
            role=role,
        )
        logger.info(f"Answer for role {role}: {answer}")
        state.cognitive.expert_answers[role] = answer
    
    if len(state.cognitive.selected_roles) == 1:
        #TODO: check this
        state.add_assistant_message(
            translate_from_eng(next(iter(state.cognitive.expert_answers.values())), state.user_lang),
            next(iter(state.cognitive.expert_answers.values()))
        )

    return state

def compare_scenarios(state: AgentState) -> AgentState:

    # check state
    if len(state.cognitive.scenario_ids) < 2:
        raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "There should be at least two active scenarios")  
    

    # load data if needed
    unavailable = [sim for sim in state.cognitive.scenario_ids if sim not in state.cognitive.data]
    if len(unavailable):
        raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "No data available")  

    state.cognitive.expert_answers = {}

    # answer user question
    for role in state.cognitive.selected_roles:

        answer = answer_question_comparison(
            question=state.get_last_user_message().content_en,
            data=state.cognitive.data,
            role=role,
        )
        state.cognitive.expert_answers[role] = answer
    
    if len(state.cognitive.selected_roles) == 1:
        #TODO: check this
        state.add_assistant_message(
            translate_from_eng(next(iter(state.cognitive.expert_answers.values())), state.user_lang),
            next(iter(state.cognitive.expert_answers.values()))
        )
        
    return state


def synthesize_answers(state: AgentState) -> AgentState:
    logger.info("Entered SYNTHESIZE_ANSWERS node")
    # Safety check
    state.add_trace("node_execution", node="synthesize_answers")
    assert len(state.cognitive.expert_answers) > 1
    
    answer = synthesize_llm(state.get_last_user_message().content_en,
                            state.cognitive.expert_answers)
    assert not answer.startswith("Error")

    logger.info(f"Synthesized answer: {answer}")
    state.add_assistant_message(
        translate_from_eng(answer, state.user_lang),
        answer
    )

    return state
