import json
from datetime import datetime
from langgraph.graph import END
from langgraph.types import Command

from ..state import AgentState, ConversationMessage
from ...utils.llm import extract_problem_data, assess_scenario_strategy
from ...utils.common import parse_confirmation
from ...utils.messages import get_message, MessageCode

def extract_problem(state: AgentState) -> AgentState:
    answer = extract_problem_data(state.get_reasoning_context(),
                                  state.cognitive.problem_info_to_extract,
                                  state.cognitive.extracted_problem_info)
    
    assert "Error connecting to Ollama" not in answer

    parsed_data = json.loads(answer)

    for key, value in parsed_data.items():
        if value:
            state.cognitive.extracted_problem_info[key] = value
    
    extracted_all_problem = True
    for key, info in state.cognitive.problem_info_to_extract.items():
        if info["required"] and key not in state.cognitive.extracted_problem_info:
            # If any required info is missing, we consider the extraction incomplete
            extracted_all_problem = False
            break
    state.cognitive.extracted_all_problem = extracted_all_problem

    return state

def decide_scenario_strategy(state: AgentState) -> AgentState:
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

    return state

def generate_scenario_candidates(state: AgentState):
    #generate base scenario first   
    #request llm for possible variations and improvements of the base scenario
    variations = [] #TODO: implement llm call to generate variations based on base scenario and problem info
    state.cognitive.scenarios_to_generate = variations
    
    return Command(update=state, goto="scenario_runner", graph=Command.PARENT)
    
def create_problem_instance_node(state: AgentState) -> AgentState:
    #TODO: call tool, assume state is changed with problem id and data
    success = True
    assert success
    state.add_assistant_message(
        get_message(MessageCode.SUCCESS_PROBLEM, state.user_lang),
        get_message(MessageCode.SUCCESS_PROBLEM, "English")
    )

def extract_problem_node(state: AgentState):

    state = extract_problem(state)

    if state.cognitive.extracted_all_problem:
        return Command(update=state, goto="WAIT_CONFIRMATION_PROBLEM")
    return Command(update=state, goto="WAIT_PROBLEM_INPUT")

def parse_confirmation_node(state: AgentState):
    message = state.get_last_user_message().content_en

    state.cognitive.next_action = parse_confirmation(message)+'_PROBLEM'

    if state.cognitive.next_action == "EDIT_PROBLEM":
        return Command(update=state, goto="extract_problem", graph=Command.PARENT)
    
    routes = {
        "CONFIRM_PROBLEM": "create_problem_instance",
        "CANCEL_PROBLEM": END,
        "WAIT_CONFIRMATION_PROBLEM": "WAIT_CONFIRMATION_PROBLEM",
    }
    return Command(update=state, goto=routes[state.cognitive.next_action])

def decide_strategy_node(state: AgentState):
    state = decide_scenario_strategy(state)
    
    if state.cognitive.next_action == "GENERATE_SCENARIOS":
        return Command(update=state, goto="scenario_extraction", graph=Command.PARENT)
    routes = {
        "GENERATE_AGENTIC_SCENARIOS": "generate_scenario_candidates",
        "ASK_USER_PREFERENCE": "WAIT_SCENARIO_PREFERENCE",
        "NO_SCENARIOS": END,
    }
    
    return Command(update=state, goto=routes[state.cognitive.next_action])