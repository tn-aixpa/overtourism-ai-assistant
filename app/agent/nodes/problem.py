import json
import logging
from langgraph.graph import END
from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import extract_problem_data, assess_scenario_strategy
from ...utils.common import parse_confirmation
from ...utils.messages import get_message, MessageCode

logger = logging.getLogger(__name__)

def extract_problem(state: AgentState) -> AgentState:
    logger.info("Extracting problem information from conversation context.")
    answer = extract_problem_data(state.get_reasoning_context(),
                                  state.cognitive.problem_info_to_extract,
                                  state.cognitive.extracted_problem_info)
    
    assert "Error connecting to chatbot" not in answer

    parsed_data = json.loads(answer)
    logger.info(f"Parsed problem information: {parsed_data}")

    for key, value in parsed_data.items():
        if value:
            state.cognitive.extracted_problem_info[key] = value
    
    extracted_all_problem = True
    for key, info in state.cognitive.problem_info_to_extract.items():
        if info["required"] and key not in state.cognitive.extracted_problem_info:
            # If any required info is missing, we consider the extraction incomplete
            extracted_all_problem = False
            break
    logger.info(f"Extracted all required problem information: {extracted_all_problem}")
    state.cognitive.extracted_all_problem = extracted_all_problem

    return state

def decide_scenario_strategy(state: AgentState) -> AgentState:
    logger.info("Deciding scenario generation strategy based on reasoning context.")
    answer = assess_scenario_strategy(state.get_reasoning_context()).strip()

    VALID_ACTIONS = {
        "GENERATE_SCENARIOS",
        "GENERATE_AGENTIC_SCENARIOS",
        "ASK_USER_PREFERENCE",
        "NO_SCENARIOS",
    }

    if answer not in VALID_ACTIONS:
        state.cognitive.next_action = "ASK_USER_PREFERENCE"
    else:
        state.cognitive.next_action = answer

    logger.info(f"Decided scenario generation strategy: {state.cognitive.next_action}")
    return state

def generate_scenario_candidates(state: AgentState):
    #generate base scenario first   
    #request llm for possible variations and improvements of the base scenario
    logger.info("Generating scenario candidates based on the extracted problem information.")
    state.add_trace("tool_call_mocked", node="generate_scenario_candidates", data={"tool": "AI scenario generation"})
    variations = [] #TODO: implement llm call to generate variations based on base scenario and problem info
    state.cognitive.scenarios_to_generate = variations
    
    return Command(update=state, goto="scenario_runner", graph=Command.PARENT)
    
def create_problem_instance_node(state: AgentState) -> AgentState:
    #TODO: call tool, assume state is changed with problem id and data
    logger.info("Creating problem instance based on the extracted problem information.")
    state.add_trace("tool_call_mocked", node="create_problem_instance_node", data={"tool": "problem_creation"})
    success = True
    assert success
    # state.add_assistant_message(
    #     get_message(MessageCode.SUCCESS_PROBLEM, state.user_lang),
    #     get_message(MessageCode.SUCCESS_PROBLEM, "English")
    # )
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

    if state.cognitive.next_action == "EDIT_PROBLEM":
        state.waiting_for = None
        return Command(update=state, goto="extract_problem", graph=Command.PARENT)
    
    routes = {
        "CONFIRM_PROBLEM": "create_problem_instance",
        "CANCEL_PROBLEM": END,
    }
    if state.cognitive.next_action == "WAIT_CONFIRMATION_PROBLEM":
        state.active_workflow = AgentState.Workflow.PROBLEM
        state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        state.user_input = None
        return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

    state.waiting_for = None
    state.user_input = None
    return Command(update=state, goto=routes[state.cognitive.next_action])

def decide_strategy_node(state: AgentState):
    logger.info("Entering scenario strategy decision node")
    state = decide_scenario_strategy(state)
    state.add_trace("node_execution", node="decide_strategy_node", data={"intent": state.cognitive.next_action})

    logger.info(f"Decided next action based on scenario strategy: {state.cognitive.next_action}")
    if state.cognitive.next_action == "GENERATE_SCENARIOS":
        state.waiting_for = None
        return Command(update=state, goto="scenario_extraction", graph=Command.PARENT)
    if state.cognitive.next_action == "GENERATE_AGENTIC_SCENARIOS":
        state.waiting_for = None
        return Command(update=state, goto="generate_scenario_candidates", graph=Command.PARENT)
    if state.cognitive.next_action == "ASK_USER_PREFERENCE":
        state.active_workflow = AgentState.Workflow.PROBLEM
        state.waiting_for = AgentState.WaitingFor.SCENARIO_PREFERENCE
        state.user_input = None
        return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)
    if state.cognitive.next_action == "NO_SCENARIOS":
        state.waiting_for = None
        state.add_assistant_message(
            get_message(MessageCode.GENRAL_EXIT_MESSAGE, state.user_lang),
            get_message(MessageCode.GENRAL_EXIT_MESSAGE, "English")
        )
        return Command(update=state, goto=END)

    raise ValueError(f"Invalid scenario strategy action: {state.cognitive.next_action}")