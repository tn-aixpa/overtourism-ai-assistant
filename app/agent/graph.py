from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from .state import AgentState

from .nodes.intent import intent_node
from .nodes.validate_intent import validate_intent_node
from .nodes.select_role import select_role
from .nodes.interact import interact_scenario
from .nodes.compare import compare_scenarios
from .nodes.synthesize import synthesize_answers
from .nodes.run_scenario import (
    extract_inputs,
    confirm,
    run_scenario,
)
from .nodes.problem_definition import (
    extract_problem,
    parse_problem_confirmation,
    decide_scenario_strategy,
    validate_scenarios,
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
# HUMAN GATE NODES (Interrupt-based)
# ─────────────────────────────────────────────

def wait_problem_input(state: AgentState):

    user_input = interrupt({
        "type": "WAIT_PROBLEM_INPUT",
        "missing_fields": state.missing_problem_fields,
    })

    return {"user_problem_input": user_input}


def wait_problem_confirmation(state: AgentState):

    decision = interrupt({
        "type": "WAIT_PROBLEM_CONFIRMATION",
        "problem": state.problem_definition,
    })

    return {"confirm_action": decision}


def wait_scenario_preference(state: AgentState):

    response = interrupt({
        "type": "WAIT_SCENARIO_PREFERENCE",
        "context": state.problem_definition,
    })

    return {"scenario_strategy_input": response}


def wait_user_scenarios(state: AgentState):

    scenarios = interrupt({
        "type": "WAIT_USER_SCENARIOS",
        "instructions": "Provide scenarios",
    })

    return {"user_scenarios": scenarios}


def wait_scenarios_confirmation(state: AgentState):

    confirmation = interrupt({
        "type": "WAIT_SCENARIOS_CONFIRMATION",
        "scenarios": state.scenarios,
    })

    return {"confirm_action": confirmation}


def wait_missing_scenario_inputs(state: AgentState):

    response = interrupt({
        "type": "WAIT_SCENARIO_INPUT",
        "missing_fields": state.missing_fields,
    })

    return {"scenario_user_input": response}

# ─────────────────────────────────────────────
# Graph definition
# ─────────────────────────────────────────────

graph = StateGraph(AgentState)

# ─── Core nodes ───────────────────────────────

graph.add_node("assess_intent", intent_node)
graph.add_node("validate_intent", validate_intent_node)
graph.add_node("select_role", select_role)
graph.add_node("interact_scenario", interact_scenario)
graph.add_node("compare_scenarios", compare_scenarios)
graph.add_node("synthesize", synthesize_answers)

# ─── Problem definition flow ──────────────────

graph.add_node("extract_problem", safe(extract_problem))
graph.add_node("WAIT_PROBLEM_INPUT", wait_problem_input)
graph.add_node("WAIT_PROBLEM_CONFIRMATION", wait_problem_confirmation)
graph.add_node("parse_problem_confirmation", parse_problem_confirmation)
graph.add_node("decide_scenario_strategy", decide_scenario_strategy)

graph.add_node("WAIT_SCENARIO_PREFERENCE", wait_scenario_preference)
graph.add_node("WAIT_USER_SCENARIOS", wait_user_scenarios)
graph.add_node("validate_scenarios", validate_scenarios)
graph.add_node("WAIT_SCENARIOS_CONFIRMATION", wait_scenarios_confirmation)
graph.add_node("generate_scenario_candidates", generate_scenario_candidates)


# ─── Scenario execution flow (single scenario) ─

graph.add_node("prepare_scenarios", prepare_scenarios)
graph.add_node("extract", safe(extract_inputs))
graph.add_node("WAIT_SCENARIO_INPUT", wait_missing_scenario_inputs)
graph.add_node("confirm", safe(confirm))
graph.add_node("run_scenario", safe(run_scenario))

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

graph.set_entry_point("assess_intent")

# ─────────────────────────────────────────────
# Intent routing
# ─────────────────────────────────────────────

graph.add_edge("assess_intent", "validate_intent")

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
        "INTERACT_SCENARIO": "interact_scenario",
        "COMPARE_SCENARIOS": "compare_scenarios",
    },
)

graph.add_conditional_edges(
    "interact_scenario",
    lambda s: "synthesize" if len(s.selected_roles) > 1 else "end",
    {
        "synthesize": "synthesize",
        "end": END,
    },
)

graph.add_conditional_edges(
    "compare_scenarios",
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
        "missing": "WAIT_SCENARIO_INPUT",
        "ready": "confirm",
    },
)

graph.add_edge("WAIT_SCENARIO_INPUT", "extract")

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
        "missing": "WAIT_PROBLEM_INPUT",
        "ready": "WAIT_PROBLEM_CONFIRMATION",
    },
)

graph.add_edge("WAIT_PROBLEM_INPUT", "extract_problem")
graph.add_edge("WAIT_PROBLEM_CONFIRMATION", "parse_problem_confirmation")

graph.add_conditional_edges(
    "parse_problem_confirmation",
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
        "ASK_USER_PREFERENCE": "WAIT_SCENARIO_PREFERENCE",
        "USER_DEFINED_SCENARIOS": "WAIT_USER_SCENARIOS",
        "AGENTIC_SCENARIOS": "generate_scenario_candidates",
    },
)

graph.add_edge("WAIT_SCENARIO_PREFERENCE", "decide_scenario_strategy")
graph.add_edge("WAIT_USER_SCENARIOS", "validate_scenarios")

# ─────────────────────────────────────────────
# USER_DEFINED_SCENARIOS definition
# ─────────────────────────────────────────────

graph.add_conditional_edges(
    "validate_scenarios",
    lambda s: "valid" if s.scenarios_valid else "missing",
    {
        "missing": "WAIT_SCENARIO_INPUT",
        "valid": "WAIT_SCENARIOS_CONFIRMATION",
    },
)

graph.add_edge("WAIT_SCENARIO_INPUT", "validate_scenarios")
graph.add_edge("WAIT_SCENARIOS_CONFIRMATION", "prepare_scenarios")


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
