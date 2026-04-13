import logging
from langgraph.types import Command

from app.agent.events import publish
from app.agent.state import AgentState
from app.utils.llm_structured_extractions import extract_problem_data
from app.utils.llm import parse_llm_json
from app.agent.nodes.general import parse_confirmation
from app.utils.messages import get_message, MessageCode
from app.utils.backend_integration_classes import ProblemInfoSchema, ProblemInfo, build_schema_data
from app.tools.backend_tools import create_problem_instance


logger = logging.getLogger(__name__)


def deactivate_current_context(state: AgentState) -> Command:
    logger.info("If there is an active context remove it")
    state.add_trace("node_execution", node="deactivate_current_context")

    if state.cognitive.active_context_type:
        state.reset_state()
    
    return state


def extract_problem(state: AgentState):
    logger.info("Entering problem extraction node")
    publish(state.session_id, "Extracting information from your input...")
    
    answer = extract_problem_data(state)   

    problem = parse_llm_json(answer)
    logger.info(f"Parsed problem information: {problem}")

    schema = ProblemInfoSchema.default()

    try:
        state.cognitive.problem_info_extracted = build_schema_data(schema, problem, ProblemInfo)
        state.cognitive.extracted_all_problem = True
    except Exception as e:
        state.cognitive.messages_to_include = [str(e)]
        state.cognitive.problem_info_extracted = None
        state.cognitive.extracted_all_problem = False    


    state.add_trace("node_execution", node="extract_problem", data={"extracted": state.cognitive.problem_info_extracted, "extracted_all": state.cognitive.extracted_all_problem})

    state.active_workflow = AgentState.Workflow.PROBLEM_CREATION
    state.user_input = None

    if state.cognitive.extracted_all_problem:
        state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
    else:
        state.waiting_for = AgentState.WaitingFor.PROBLEM_INPUT

    return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

def parse_problem_confirmation(state):
    return parse_confirmation(state, "PROBLEM")

def create_problem(state: AgentState) -> AgentState:
    state.add_trace("node_execution", node="create_problem_instance")
    publish(state.session_id, "Creating problem instance based on the extracted information")
    
    problem = state.cognitive.problem_info_extracted
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
    state.cognitive.messages_to_include = [get_message(MessageCode.SUCCESSFUL_INSTANCE_CREATION, instance="problem")]
    state.cognitive.additional_output_information = []

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)