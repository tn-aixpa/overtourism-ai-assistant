import logging
from langgraph.types import Command
from langgraph.graph import  END

from app.agent.state import AgentState
from app.config import ALLOWED_ROLES
from app.utils.llm_reasoning import select_role_llm
from app.utils.llm_text_generation import answer_question

from app.utils.error_codes import ErrorCode, get_error_message

logger = logging.getLogger(__name__)

def assert_active_context(state: AgentState) -> Command:
    logger.info("Checking if there is an active context")
    state.add_trace("node_execution", node="assert_active_context")

    if state.cognitive.active_context_type:
        return Command(update=state, goto="select_role")

    state.cognitive.messages_to_include = [get_error_message(ErrorCode.INVALID_CONTEXT, "English")]
    state.cognitive.additional_output_information = [
        f"Active contex: {state.get_active_context_string()}",
        state.cognitive.allowed_operations
    ]
    if state.cognitive.active_context_type == "":
        if state.cognitive.available_entries:
            available_problems = state.cognitive.available_entries["ids_dict"]["problems"]
            state.cognitive.additional_output_information.append(
                "Available problems are: " + ", ".join(available_problems) 
            )

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)


def select_role(state: AgentState) -> AgentState:
    # question = state.get_last_user_message().content_en
    # raw = select_role_llm(question, ALLOWED_ROLES)

    # if "Error" in raw:
    #     roles = ["Data Analyst"]
    #     return state
    
    # # ---- Parse & normalize ----
    # roles = []
    # for r in raw.split(","):
    #     key = r.strip()
    #     roles.append(key)

    # if not roles:
    #     roles = ["Data Analyst"]
    
    # state.cognitive.selected_roles = roles

    # logger.info(f"Selected roles: {roles}")

    state.cognitive.selected_roles = ["Data Analyst"]
    return state

def interact_context(state: AgentState) -> AgentState:

    state.cognitive.expert_answers = {}

    # answer user question
    state.cognitive.messages_to_include = []
    state.cognitive.additional_output_information = []
    for role in state.cognitive.selected_roles:
        answer = answer_question(
            question=state.get_last_user_message().content_en,
            data=state.cognitive.context_data,
            role=role,
            messages=state.get_reasoning_context(),
            language=state.user_lang
        ).strip()
        logger.info(f"Answer for role {role}: {answer}")
        state.cognitive.messages_to_include.append(f"{role} answered: {answer}")
    
    if len(state.cognitive.selected_roles) > 1:
        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)
        

    state.cognitive.messages_to_include = []
    state.add_assistant_message(
        answer,
        answer
    )
    return Command(update=state, goto=END, graph=Command.PARENT)
