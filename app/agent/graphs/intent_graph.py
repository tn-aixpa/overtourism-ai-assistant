from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ..nodes.intent import intent_node, validate_intent_node
from .problem_graph import problem_subgraph
from .scenario_graph import scenario_runner_subgraph


# ---- Command wrappers

def route_from_intent(state: AgentState):
    action = state.next_action
    if action in ["INTERACT_SCENARIO", "COMPARE_SCENARIOS"]:
        return Command(update=state, goto="interaction", graph=Command.PARENT)

    # Scenario runner subgraph

    if action == "RUN_NEW_SCENARIO":
        return Command(update=state, goto="extract", graph=Command.PARENT)

    if action == "CREATE_PROBLEM":
        return Command(update=state, goto="extract_problem", graph=Command.PARENT)

    # END nodes
    if action in ["NOT_ALLOWED", "INVALID"]:
        return Command(update=state, goto=END)
    

    # Fallback safety
    return Command(update=state, goto="error", graph=Command.PARENT)

# ---- Build subgraph

intent_graph = StateGraph(AgentState)

intent_graph.add_node("assess_intent", intent_node)
intent_graph.add_node("validate_intent", validate_intent_node)
intent_graph.add_node("route_intent", route_from_intent)

intent_graph.set_entry_point("assess_intent")

intent_graph.add_edge("assess_intent", "validate_intent")
intent_graph.add_edge("validate_intent", "route_intent")

intent_subgraph = intent_graph.compile()

