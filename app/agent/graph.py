from langgraph.graph import StateGraph, END
from .state import AgentState

from .nodes.intent import intent_node
from .nodes.validate_intent import validate_intent_node
from .nodes.select_role import select_role
from .nodes.interact import interact_scenario
from .nodes.compare import compare_scenarios
from .nodes.run_scenario import (
    extract_inputs,
    ask_missing as ask_missing_scenario,
    confirm,
    run_scenario,
)
from .nodes.error_recovery import error_recovery_node
from .nodes.synthesize import synthesize_answers
from .nodes.problem_definition import (
    extract_problem,
    ask_missing_problem,
    confirm_problem,
    decide_scenario_strategy,
    ask_scenario_preference,
    collect_user_scenarios,
    validate_scenarios,
    confirm_user_scenarios,
    generate_scenario_candidates,
)

def safe_extract_inputs(state):
    try:
        return extract_inputs(state)
    except Exception as e:
        return error_recovery_node(state, str(e))

def safe_confirm(state):
    try:
        return confirm(state)
    except Exception as e:
        return error_recovery_node(state, str(e))

def safe_run_scenario(state):
    try:
        return run_scenario(state)
    except Exception as e:
        return error_recovery_node(state, str(e))
    
def safe_extract_problem(state):
    try:
        return extract_problem(state)
    except Exception as e:
        return error_recovery_node(state, str(e))

def safe_confirm_problem(state):
    try:
        return confirm_problem(state)
    except Exception as e:
        return error_recovery_node(state, str(e))
    
# --- Define GRAPH ---

graph = StateGraph(AgentState)

# Core nodes
graph.add_node("intent", intent_node)
graph.add_node("validate_intent", validate_intent_node)
graph.add_node("select_role", select_role)
graph.add_node("synthesize", synthesize_answers)
graph.add_node("interact", interact_scenario)
graph.add_node("compare", compare_scenarios)

# Problem flow nodes
graph.add_node("extract_problem", safe_extract_problem)
graph.add_node("ask_missing_problem", ask_missing_problem)
graph.add_node("confirm_problem", safe_confirm_problem)
graph.add_node("decide_scenario_strategy", decide_scenario_strategy)
graph.add_node("ask_scenario_preference", ask_scenario_preference)
graph.add_node("collect_user_scenarios", collect_user_scenarios)
graph.add_node("validate_scenarios", validate_scenarios)
graph.add_node("confirm_user_scenarios", confirm_user_scenarios)
graph.add_node("generate_scenario_candidates", generate_scenario_candidates)

# Scenario flow nodes
graph.add_node("ask_missing_scenario", ask_missing_scenario)
graph.add_node("extract", safe_extract_inputs)
graph.add_node("confirm", safe_confirm)
graph.add_node("run_scenario", safe_run_scenario)

# Edges definitions
graph.set_entry_point("intent")
graph.add_edge("intent", "validate_intent")

graph.add_conditional_edges(
    "validate_intent",
    lambda s: s.next_action,
    {
        "INTERACT_SCENARIO": "select_role",
        "COMPARE_SCENARIOS": "select_role",
        "RUN_NEW_SCENARIO": "extract",
        "CREATE_PROBLEM": "extract_problem",
        "NOT_ALLOWED": END,
        "INVALID": END,
    },
)

graph.add_conditional_edges(
    "select_role",
    lambda s: s.next_action,
    {
        "INTERACT_SCENARIO": "interact",
        "COMPARE_SCENARIOS": "compare",
    },
)

graph.add_conditional_edges(
    "interact",
    lambda s: "synthesize" if len(s.selected_roles) > 1 else "end",
    {
        "synthesize": "synthesize",
        "end": END,
    },
)

graph.add_conditional_edges(
    "compare",
    lambda s: "synthesize" if len(s.selected_roles) > 1 else "end",
    {
        "synthesize": "synthesize",
        "end": END,
    },
)

graph.add_conditional_edges(
    "extract",
    lambda s: "ready" if s.current_input else "missing",
    {
        "missing": "ask_missing_scenario",
        "ready": "confirm",
    },
)

graph.add_edge("ask_missing_scenario", "extract")

graph.add_conditional_edges(
    "confirm",
    lambda s: s.confirm_action,
    {
        "RUN": "run_scenario",
        "EDIT": "extract",
        "CANCEL": END,
    },
)

graph.add_conditional_edges(
    "extract_problem",
    lambda s: "ready" if s.problem_data else "missing",
    {
        "missing": "ask_missing_problem",
        "ready": "confirm_problem",
    },
)
graph.add_edge("ask_missing_problem", "extract_problem")

graph.add_edge("confirm_problem", "decide_scenario_strategy")

graph.add_conditional_edges(
    "decide_scenario_strategy",
    lambda s: s.scenario_strategy,
    {
        "NO_SCENARIOS": END,
        "ASK_USER_PREFERENCE": "ask_scenario_preference",
        "USER_DEFINED_SCENARIOS": "collect_user_scenarios",
        "AGENTIC_SCENARIOS": "generate_scenario_candidates",
    },
)

graph.add_edge("ask_scenario_preference", "decide_scenario_strategy")

graph.add_conditional_edges(
    "validate_scenarios",
    lambda s: "valid" if s.scenarios_valid else "missing",
    {
        "missing": "ask_missing_scenario",
        "valid": "confirm_user_scenarios",
    },
)
graph.add_edge("ask_missing_scenario", "validate_scenarios")
graph.add_edge("confirm_user_scenarios", "extract")
graph.add_edge("generate_scenario_candidates", "extract")

graph.add_edge("run_scenario", END)

app = graph.compile()
