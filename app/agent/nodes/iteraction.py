import logging
from langgraph.types import Command
from langgraph.graph import  END

from app.agent.events import publish
from app.agent.state import AgentState
from app.config import ALLOWED_ROLES
from app.utils.llm_reasoning import select_role_llm
from app.utils.llm_text_generation import answer_question
from app.tools.backend_tools_temp import generate_chart
from app.config import SYSTEM_DESCRIPTION

from app.utils.messages import get_message, MessageCode

logger = logging.getLogger(__name__)

def assert_active_context(state: AgentState) -> Command:
    logger.info("Checking if there is an active context")
    state.add_trace("node_execution", node="assert_active_context")

    if state.cognitive.active_context_type:
        return Command(update=state, goto="select_role")

    state.cognitive.messages_to_include = [get_message(MessageCode.INVALID_CONTEXT)]
    state.cognitive.additional_output_information = [
        f"Active contex: {state.get_active_context_string()}",
        SYSTEM_DESCRIPTION
    ]
    if state.cognitive.active_context_type == "":
        if state.cognitive.available_entries:
            available_problems = state.cognitive.available_entries["ids_dict"]["problems"]
            state.cognitive.additional_output_information.append(
                "Available problems are: " + ", ".join(available_problems) 
            )

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)


def select_role(state: AgentState) -> AgentState:
    # raw = select_role_llm(state)

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
    publish(state.session_id, "Collecting relevant information and generating answer")

    # answer user question
    state.cognitive.messages_to_include = []
    state.cognitive.additional_output_information = []
    logger.info(f"Selected roles: {state.cognitive.selected_roles}")
    for role in state.cognitive.selected_roles:
        answer, draw = answer_question(state, role)
        logger.info(f"Answer for role {role}: {answer}")
        state.cognitive.messages_to_include.append(f"{role} answered: {answer}")
    
    # TODO: consider moving somewhere else or improving
    last_user_message = state.get_last_user_message().content.lower()

    if draw and state.cognitive.active_context_type == "scenario":
        if len(state.cognitive.active_context) > 1:
            state.chart_data = generate_chart("comparison_bar")
        else:
            if any(keyword in last_user_message for keyword in ["carico", "load"]):
                state.chart_data = generate_chart("tourist_load")
            else:
                state.chart_data = generate_chart("tourists_excursionists")


    if len(state.cognitive.selected_roles) > 1:
        state.reset_state(
            reset_listing=True,
            reset_new_problem=True,
            reset_new_proposal=True,
            reset_new_scenario=True,
            reset_errors=True,
            reset_context=False,
            reset_data=False
        )
        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)
        

    state.reset_state(
        reset_listing=True,
        reset_new_problem=True,
        reset_new_proposal=True,
        reset_new_scenario=True,
        reset_errors=True,
        reset_context=False,
        reset_data=False
    )
    state.add_assistant_message(
        answer
    )
    if state.integrated_mode:
        return Command(update=state, goto=END)

    return Command(update=state, goto=END, graph=Command.PARENT)
