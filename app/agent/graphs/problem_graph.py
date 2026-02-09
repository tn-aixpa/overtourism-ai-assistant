from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ..nodes.problem_definition import (
    extract_problem,
    parse_problem_confirmation,
    decide_scenario_strategy,
    validate_scenarios,
    generate_scenario_candidates,
)

from .utils import human_gate, safe
from .scenario_graph import scenario_runner_subgraph

# ---- Human gates

wait_problem_input = human_gate(
    "WAIT_PROBLEM_INPUT",
    "user_problem_input",
    lambda s: {"missing_fields": s.missing_problem_fields},
)

wait_problem_confirmation = human_gate(
    "WAIT_PROBLEM_CONFIRMATION",
    "confirm_action",
    lambda s: {"problem": s.problem_definition},
)

wait_scenario_preference = human_gate(
    "WAIT_SCENARIO_PREFERENCE",
    "scenario_strategy_input",
    lambda s: {"context": s.problem_definition},
)

wait_user_scenarios = human_gate(
    "WAIT_USER_SCENARIOS",
    "user_scenarios",
    lambda s: {"instructions": "Provide scenarios"},
)

wait_scenarios_confirmation = human_gate(
    "WAIT_SCENARIOS_CONFIRMATION",
    "confirm_action",
    lambda s: {"scenarios": s.scenarios},
)

wait_missing_scenario_inputs = human_gate(
    "WAIT_SCENARIO_INPUT",
    "scenario_user_input",
    lambda s: {"missing_fields": s.missing_fields},
)

# ---- Command wrappers

def extract_problem_node(state: AgentState):
    state = safe(extract_problem)(state)
    if state.extracted_all_problem:
        return Command(update=state, goto="WAIT_PROBLEM_CONFIRMATION")
    return Command(update=state, goto="WAIT_PROBLEM_INPUT")

def parse_confirmation_node(state: AgentState):
    state = parse_problem_confirmation(state)
    routes = {
        "CONFIRM": "decide_scenario_strategy",
        "EDIT": "extract_problem",
        "CANCEL": END,
    }
    return Command(update=state, goto=routes[state.confirm_action])

def decide_strategy_node(state: AgentState):
    state = decide_scenario_strategy(state)

    # Senior architecture: delegate to scenario runner subgraph
    if state.scenario_strategy == "NO_SCENARIOS":
        return Command(update=state, goto=END)

    # Any strategy that requires running scenarios → subgraph
    if state.scenario_strategy in ["ASK_USER_PREFERENCE", "USER_DEFINED_SCENARIOS", "AGENTIC_SCENARIOS"]:
        return Command(update=state, graph=scenario_runner_subgraph, goto="extract") #TODO edit this to correct version

    return Command(update=state, goto=END)

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
problem_subgraph = graph.compile()
