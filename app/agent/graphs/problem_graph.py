from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ..nodes.problem_definition import (
    extract_problem,
    decide_scenario_strategy,
    validate_scenarios,
    generate_scenario_candidates,
)

from .utils import human_gate, safe

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
