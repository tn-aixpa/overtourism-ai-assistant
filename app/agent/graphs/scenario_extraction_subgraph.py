from langgraph.graph import StateGraph

from app.agent.nodes.scenario import extract_scenario_node, parse_confirmation_node
from app.agent.state import AgentState
from app.agent.graphs.utils import add_safe_node


def scenario_entry_router(state: AgentState):
    """
    Resume into the correct internal node based on `state.waiting_for`.
    """
    if state.waiting_for == AgentState.WaitingFor.SCENARIO_CONFIRMATION:
        return "parse_scenario_confirmation"
    # Default (including SCENARIO_INPUT and first entry)
    return "extract_scenario"

# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("scenario_entry_router", lambda s: s)
add_safe_node(graph, "extract_scenario", extract_scenario_node)
add_safe_node(graph, "parse_scenario_confirmation", parse_confirmation_node)

graph.set_entry_point("scenario_entry_router")

graph.add_conditional_edges(
    "scenario_entry_router",
    scenario_entry_router,
    {
        "parse_scenario_confirmation": "parse_scenario_confirmation",
        "extract_scenario": "extract_scenario",
    }
)

scenario_extraction_subgraph = graph.compile()
