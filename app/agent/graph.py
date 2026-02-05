from langgraph.graph import StateGraph, END
from .state import AgentState

from .nodes.intent import intent_node
from .nodes.validate_intent import validate_intent_node
from .nodes.select_role import select_role
from .nodes.interact import interact_scenario
from .nodes.compare import compare_scenarios
from .nodes.synthesize import synthesize_answers
from .nodes.run_scenario import (
    extract_inputs,
    ask_missing as ask_missing_scenario,
    confirm,
    run_scenario,
)
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
from .nodes.prepare_scenarios import prepare_scenarios
from .nodes.error_recovery import error_recovery_node


# ─────────────────────────────────────────────
# Safe wrappers
# ─────────────────────────────────────────────


def safe(node_fn):
    def _safe(state):
        try:
            return node_fn(state)
        except Exception as e:
            return error_recovery_node(state, str(e))

    return _safe


# ─────────────────────────────────────────────
# Graph definition
# ─────────────────────────────────────────────

graph = StateGraph(AgentState)

# ─── Core nodes ───────────────────────────────

graph.add_node("intent", intent_node)
graph.add_node("validate_intent", validate_intent_node)
graph.add_node("select_role", select_role)
graph.add_node("interact", interact_scenario)
graph.add_node("compare", compare_scenarios)
graph.add_node("synthesize", synthesize_answers)

# ─── Problem definition flow ──────────────────

graph.add_node("extract_problem", safe(extract_problem))
graph.add_node("ask_missing_problem", ask_missing_problem)
graph.add_node("confirm_problem", safe(confirm_problem))
graph.add_node("decide_scenario_strategy", decide_scenario_strategy)

graph.add_node("ask_scenario_preference", ask_scenario_preference)
graph.add_node("collect_user_scenarios", collect_user_scenarios)
graph.add_node("validate_scenarios", validate_scenarios)
graph.add_node("confirm_user_scenarios", confirm_user_scenarios)
graph.add_node("generate_scenario_candidates", generate_scenario_candidates)

# ─── Scenario execution flow (single scenario) ─

graph.add_node("prepare_scenarios", prepare_scenarios)
graph.add_node("extract", safe(extract_inputs))
graph.add_node("ask_missing_scenario", ask_missing_scenario)
graph.add_node("confirm", safe(confirm))
graph.add_node("run_scenario", safe(run_scenario))

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

graph.set_entry_point("intent")

# ─────────────────────────────────────────────
# Intent routing
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
# Interaction / comparison
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
# RUN_NEW_SCENARIO (single scenario)
# ─────────────────────────────────────────────

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

# ─────────────────────────────────────────────
# CREATE_PROBLEM flow
# ─────────────────────────────────────────────

graph.add_conditional_edges(
    "extract_problem",
    lambda s: "ready" if s.extracted_all_problem else "missing",
    {
        "missing": "ask_missing_problem",
        "ready": "confirm_problem",
    },
)

graph.add_edge("ask_missing_problem", "extract_problem")

graph.add_conditional_edges(
    "confirm_problem",
    lambda s: s.confirm_action,
    {
        "CONFIRM": "decide_scenario_strategy",
        "EDIT": "extract_problem",
        "CANCEL": END,
    },
)

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

# ─────────────────────────────────────────────
# USER_DEFINED_SCENARIOS definition
# ─────────────────────────────────────────────

graph.add_edge("collect_user_scenarios", "validate_scenarios")

graph.add_conditional_edges(
    "validate_scenarios",
    lambda s: "valid" if s.scenarios_valid else "missing",
    {
        "missing": "ask_missing_scenario",
        "valid": "confirm_user_scenarios",
    },
)

graph.add_edge("ask_missing_scenario", "validate_scenarios")

graph.add_edge("confirm_user_scenarios", "prepare_scenarios")

# ─────────────────────────────────────────────
# AGENTIC_SCENARIOS
# ─────────────────────────────────────────────

graph.add_edge("generate_scenario_candidates", "prepare_scenarios")

# ─────────────────────────────────────────────
# Scenario batch execution
# ─────────────────────────────────────────────

graph.add_edge("prepare_scenarios", "run_scenario")

graph.add_conditional_edges(
    "run_scenario",
    lambda s: "more" if s.has_pending_scenarios else "done",
    {
        "more": "prepare_scenarios",
        "done": END,
    },
)

# ─────────────────────────────────────────────
# Compile
# ─────────────────────────────────────────────

app = graph.compile()
