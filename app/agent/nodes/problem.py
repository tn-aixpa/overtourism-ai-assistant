import json
from langgraph.graph import END
from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import extract_problem_data
from ...utils.llm import assess_scenario_strategy

def extract_problem(state: AgentState) -> AgentState:
    answer = extract_problem_data(state.messages[-1]["content"] if state.messages else "",
                                  state.problem_info_to_extract,
                                  state.extracted_problem_info)
    
    assert "Error connecting to Ollama" not in answer

    try:
        # The LLM output should be JSON, so we load it
        parsed_data = json.loads(answer)
    except json.JSONDecodeError:
        return {}

    for key, value in parsed_data.items():
        if value:
            state.extracted_problem_info[key] = value
    
    extracted_all_problem = True
    for key, info in state.problem_info_to_extract.items():
        if info["required"] and key not in state.extracted_problem_info:
            # If any required info is missing, we consider the extraction incomplete
            extracted_all_problem = False
            break
    state.extracted_all_problem = extracted_all_problem

    return state

def decide_scenario_strategy(state: AgentState) -> AgentState:
    answer = assess_scenario_strategy(state.messages).strip()

    VALID_ACTIONS = {
        "GENERATE_SCENARIOS",
        "GENERATE_AGENTIC_SCENARIOS",
        "ASK_USER_PREFERENCE",
        "NO_SCENARIOS",
    }

    if answer not in VALID_ACTIONS:
        state.next_action = "ASK_USER_PREFERENCE"
    else:
        state.next_action = answer.strip()
    return state

def generate_scenario_candidates(state: AgentState):
    #generate base scenario first
    #TODO: implement, for now we just load a base scenario from file
    with open("tests/data/test_scenarios.json", "r") as f:
        base_scenario = json.load(f)
        state.data = base_scenario

    if not state.data:
        state.messages.append({"role": "assistant", "content": "Error generating scenarios. Please try again later."})
        return Command(update=state, goto="END")
    
    #request llm for possible variations and improvements of the base scenario
    variations = [] #TODO: implement llm call to generate variations based on base scenario and problem info
    state.scenarios_to_generate = variations
    return Command(update=state, goto="scenario_runner", graph=Command.PARENT)
    
def create_problem_instance_node(state: AgentState) -> AgentState:
    #TODO: call tool, assume state is changed with problem id and data
    success = True
    assert success
    return Command(update=state, goto="decide_scenario_strategy")

def extract_problem_node(state: AgentState):
    state = extract_problem(state)
    if state.extracted_all_problem:
        return Command(update=state, goto="WAIT_PROBLEM_CONFIRMATION")
    return Command(update=state, goto="WAIT_PROBLEM_INPUT")

def parse_confirmation_node(state: AgentState):
    message = state.messages[-1]["content"].lower() if state.messages else ""
    if any(word in message for word in ["yes", "confirm", "ok"]):
        state.next_action = "CONFIRM_PROBLEM"
    elif any(word in message for word in ["edit", "change", "modify"]):
        state.next_action = "EDIT_PROBLEM"
    elif any(word in message for word in ["cancel", "interrut", "quit"]) or message == "no":
        state.next_action = "CANCEL_PROBLEM"
    else:
        state.next_action = "WAIT_PROBLEM_CONFIRMATION"
    #TODO: add also llm fallback

    routes = {
        "CONFIRM_PROBLEM": "decide_scenario_strategy",
        "EDIT_PROBLEM": "extract_problem",
        "CANCEL_PROBLEM": END,
        "WAIT_PROBLEM_CONFIRMATION": "WAIT_PROBLEM_CONFIRMATION",
    }
    return Command(update=state, goto=routes[state.next_action], graph=Command.PARENT)

def decide_strategy_node(state: AgentState):
    state = decide_scenario_strategy(state)

    if state.next_action == "GENERATE_SCENARIOS":
        return Command(update=state, goto="scenario_extraction", )
    routes = {
        "GENERATE_SCENARIOS": "generate_scenario_candidates",
        "GENERATE_AGENTIC_SCENARIOS": "generate_scenario_candidates",
        "ASK_USER_PREFERENCE": "WAIT_SCENARIO_PREFERENCE",
        "NO_SCENARIOS": END,
    }
    
    return Command(update=state, goto=routes[state.next_action])