import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm_structured_extractions import extract_problem_data
from app.utils.llm import parse_llm_json
from app.utils.common import parse_confirmation
from app.utils.messages import get_message, MessageCode
from app.utils.backend_integration_classes import ProblemInfoSchema, ProblemInfo, build_schema_data
from app.tools.backend_tools import create_problem_instance


logger = logging.getLogger(__name__)


def deactive_current_context(state: AgentState) -> Command:
    logger.info("If there is an active context remove it")
    state.add_trace("node_execution", node="deactive_current_context")

    if state.cognitive.active_context_type:
        state.reset_state()
    
    return state

def extract_problem(state: AgentState) -> AgentState:
    logger.info("Extracting problem information from conversation context.")
    atttachments_list = []

    answer = extract_problem_data(
        state.get_reasoning_context(),
        state.cognitive.problem_info_to_extract,
        atttachments_list
    )

    assert "Error connecting to chatbot" not in answer

    problem = parse_llm_json(answer)
    logger.info(f"Parsed problem information: {problem}")

    schema = ProblemInfoSchema.default()

    try:
        state.cognitive.extracted_problem_info = build_schema_data(schema, problem, ProblemInfo)
        state.cognitive.extracted_all_problem = True
    except Exception as e:
        state.cognitive.messages_to_include = [str(e)]
        state.cognitive.extracted_problem_info = None
        state.cognitive.extracted_all_problem = False

    return state


def extract_problem_node(state: AgentState):
    logger.info("Entering problem extraction node")
    state = extract_problem(state)

    state.add_trace("node_execution", node="extract_problem_node", data={"extracted": state.cognitive.extracted_problem_info, "extracted_all": state.cognitive.extracted_all_problem})

    state.active_workflow = AgentState.Workflow.PROBLEM
    state.user_input = None

    if state.cognitive.extracted_all_problem:
        state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
    else:
        state.waiting_for = AgentState.WaitingFor.PROBLEM_INPUT

    return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

def parse_confirmation_node(state: AgentState):
    logger.info("Entering confirmation parsing node")
    message = state.get_last_user_message().content_en

    state.cognitive.next_action = parse_confirmation(message)+'_PROBLEM'
    logger.info(f"Parsed user confirmation intent: {state.cognitive.next_action}")

    state.add_trace("node_execution", node="parse_confirmation_node", data={"intent": state.cognitive.next_action})

    if state.cognitive.next_action == "WAIT_CONFIRMATION_PROBLEM":
        state.active_workflow = AgentState.Workflow.PROBLEM
        state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        state.user_input = None
        return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)
    
    if state.cognitive.next_action == "CONFIRM_PROBLEM":
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto="create_new_problem_instance")
    
    if state.cognitive.next_action == "CANCEL_PROPOSAL":
        state.waiting_for = None
        state.user_input = None
        state.active_workflow = None
        state.cognitive.messages_to_include = [get_message(MessageCode.GENRAL_EXIT_MESSAGE, "English")]
        state.cognitive.additional_output_information = []
        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)


    if state.cognitive.next_action == "EDIT_PROBLEM":
        state.waiting_for = None

    state.waiting_for = None
    state.user_input = None
    return Command(update=state, goto="deactive_current_context", graph=Command.PARENT)

def create_new_problem_instance_node(state: AgentState) -> AgentState:
    state.add_trace("node_execution", node="create_new_problem_instance_node")
    
    problem = state.cognitive.extracted_problem_info
    logger.info(f"Creating instance for problem: {problem}")
    
    payload = {
        "problem_name": problem.problem_title,
        "problem_description": problem.problem_description,
        # "created": "string",
        # "updated": "string",
        "objective": problem.objectives,
        "groups": problem.available_subsystems,
        "links": problem.additional_data,
        # "proposals": []
    }

    # remove empty fields (recommended)
    payload = {k: v for k, v in payload.items() if v not in [None, "", [], {}]}

    result = create_problem_instance.invoke({
        "payload": payload,
    })


    logger.info(result)

    state.resume_nome = {}
    state.active_workflow = None
    state.cognitive.messages_to_include = [get_message(MessageCode.SUCCESS_PROBLEM, "English")]
    state.cognitive.additional_output_information = []

    #TODO: decide if we want to activate this problem or ask the user if he wants to activate it

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)