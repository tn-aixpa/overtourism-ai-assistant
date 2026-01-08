from langgraph.graph import StateGraph, END
from state import AgentState

from nodes.intent import intent_node
from nodes.validate_intent import validate_intent_node
from nodes.interact import interact_simulation
from nodes.compare import compare_simulations
from nodes.run_simulation import (
    extract_inputs,
    ask_missing,
    confirm,
    run_simulation,
)
from nodes.error_recovery import error_recovery_node

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

def safe_run_simulation(state):
    try:
        return run_simulation(state)
    except Exception as e:
        return error_recovery_node(state, str(e))
    
# --- Define GRAPH ---

graph = StateGraph(AgentState)

graph.add_node("intent", intent_node)
graph.add_node("validate_intent", validate_intent_node)
graph.add_node("interact", interact_simulation)
graph.add_node("compare", compare_simulations)
graph.add_node("ask_missing", ask_missing)
graph.add_node("extract", safe_extract_inputs)
graph.add_node("confirm", safe_confirm)
graph.add_node("run_sim", safe_run_simulation)

graph.set_entry_point("intent")
graph.add_edge("intent", "validate_intent")


graph.add_conditional_edges(
    "validate_intent",
    lambda s: s["next_action"],
    {
        "INTERACT_SIMULATION": "interact",
        "COMPARE_SIMULATIONS": "compare",
        "RUN_NEW_SIMULATION": "extract",
        "NOT_ALLOWED": END,
        "INVALID": END,
    },
)

graph.add_conditional_edges(
    "extract",
    lambda s: "missing" if s["missing_inputs"] else "ready",
    {
        "missing": "ask_missing",
        "ready": "confirm",
    },
)

graph.add_edge("ask_missing", END)
graph.add_edge("confirm", "run_sim")
graph.add_edge("run_sim", END)

app = graph.compile()
