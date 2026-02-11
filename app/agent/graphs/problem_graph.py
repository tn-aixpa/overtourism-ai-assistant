import json
from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import extract_problem_data
from ...utils.llm import assess_scenario_strategy
from .utils import human_gate, safe

# ---- Nodes


def extract_problem(state: AgentState) -> AgentState:
    answer = extract_problem_data(state.messages[-1]["content"] if state.messages else "",
                                  state.problem_info,
                                  state.extracted_problem_info)
    
    #"problem_title": "Insufficient Parking Spaces in Molveno",\n  "objectives": "To provide sufficient parking spaces, reduce off-spot parking, and eliminate long queues",\n  "problem_description": "The lack of parking spaces in Molveno results in people parking off-spot and forming long queues. This issue needs to be addressed to ensure smooth traffic flow and prevent congestion.",\n  "additional_data": "The current situation is causing inconvenience to visitors and locals alike.",\n  "available_subsystems": "Parking management, Traffic management, Urban planning"\n}',

    if "Error connecting to Ollama" not in answer:

        try:
            # The LLM output should be JSON, so we load it
            parsed_data = json.loads(answer)
        except json.JSONDecodeError:
            return {}

        for key, value in parsed_data.items():
            if value:
                state.extracted_problem_info[key] = value
        
        extracted_all_problem = True
        for key, info in state.problem_info.items():
            if info["required"] and key not in state.extracted_problem_info:
                # If any required info is missing, we consider the extraction incomplete
                extracted_all_problem = False
                break
        state.extracted_all_problem = extracted_all_problem

    else:
      #TODO: impement
      pass
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

def validate_scenarios():
    pass

def generate_scenario_candidates():
    pass

def create_problem_instance_node(state: AgentState) -> AgentState:
    #TODO: implement
    success = True
    if success:
        return Command(update=state, goto="decide_scenario_strategy")
    else:
        state.messages.append({"role": "assistant", "content": "There was an error creating the problem instance. Please try again later."})
        return Command(update=state, goto="END")

# ---- Human gates

wait_problem_input = human_gate(
    "WAIT_PROBLEM_INPUT",
    lambda s: {"instructions": f"To create correctly create the new problem, please provide the missing information: {chr(10)} - {chr(10).join(k for k in s.problem_info if k not in s.extracted_problem_info)}. {chr(10)}"},
)

wait_problem_confirmation = human_gate(
    "WAIT_PROBLEM_CONFIRMATION",
    lambda s: {"instructions": "Do you confirm the extracted problem information?", "problem_info": s.extracted_problem_info},
)

wait_scenario_preference = human_gate(
    "WAIT_SCENARIO_PREFERENCE",
    lambda s: {"instructions": "Do you want to create scenarios for this problem? If so, do you have specific scenarios in mind or would you like the system to generate some based on the problem information?"},
)

wait_user_scenarios = human_gate(
    "WAIT_USER_SCENARIOS",
    lambda s: {"instructions": "Provide scenarios"},
)

wait_scenarios_confirmation = human_gate(
    "WAIT_SCENARIOS_CONFIRMATION",
    lambda s: {"scenarios": s.scenarios},
)

wait_missing_scenario_inputs = human_gate(
    "WAIT_SCENARIO_INPUT",
    lambda s: {"missing_fields": s.missing_fields},
)

# ---- Command wrappers

def extract_problem_node(state: AgentState):
    with open("logs/debugger.log", "w") as f:
        f.write(f"Extracting problem\n")
        try:
            state = safe(extract_problem)(state)
            f.write(f"State after extraction: {state}\n")
            f.write(f"Extracted problem info: {state.extracted_problem_info}\n")
            if state.extracted_all_problem:
                f.write("All problem info extracted successfully.")
                return Command(update=state, goto="WAIT_PROBLEM_CONFIRMATION")
            f.write("Problem info extraction incomplete.")
            return Command(update=state, goto="WAIT_PROBLEM_INPUT")
        except Exception as e:
            f.write(f"Error during problem extraction: {e}")

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
    return Command(update=state, goto=routes[state.next_action])

def decide_strategy_node(state: AgentState):
    state = decide_scenario_strategy(state)

    routes = {
        "GENERATE_SCENARIOS": "generate_scenario_candidates",
        "GENERATE_AGENTIC_SCENARIOS": "generate_scenario_candidates",
        "ASK_USER_PREFERENCE": "WAIT_SCENARIO_PREFERENCE",
        "NO_SCENARIOS": END,
    }
    
    return Command(update=state, goto=routes[state.next_action])

def validate_scenarios_node(state: AgentState):
    state = validate_scenarios(state)
    if state.scenarios_valid:
        return Command(update=state, goto="WAIT_SCENARIOS_CONFIRMATION")
    return Command(update=state, goto="WAIT_USER_SCENARIOS")

# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("extract_problem", extract_problem_node)
graph.add_node("WAIT_PROBLEM_INPUT", wait_problem_input)
graph.add_node("WAIT_PROBLEM_CONFIRMATION", wait_problem_confirmation)
graph.add_node("parse_problem_confirmation", parse_confirmation_node)
graph.add_node("create_problem_instance", create_problem_instance_node)
graph.add_node("decide_scenario_strategy", decide_strategy_node)
graph.add_node("WAIT_SCENARIO_PREFERENCE", wait_scenario_preference)
graph.add_node("WAIT_USER_SCENARIOS", wait_user_scenarios)
graph.add_node("validate_scenarios", validate_scenarios_node)
graph.add_node("WAIT_SCENARIOS_CONFIRMATION", wait_scenarios_confirmation)
graph.add_node("generate_scenario_candidates", generate_scenario_candidates)

graph.set_entry_point("extract_problem")

graph.add_edge("WAIT_PROBLEM_CONFIRMATION", "parse_problem_confirmation")
graph.add_edge("WAIT_SCENARIO_PREFERENCE", "decide_scenario_strategy")
graph.add_edge("WAIT_PROBLEM_INPUT", "extract_problem")

problem_subgraph = graph.compile()
