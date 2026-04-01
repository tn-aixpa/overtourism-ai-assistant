from langgraph.graph import StateGraph

from app.agent.nodes.problem import deactive_current_context, extract_problem_node, parse_confirmation_node, create_new_problem_instance_node
from app.agent.state import AgentState
from app.agent.graphs.utils import add_safe_node

# ---- Build subgraph

def problem_entry_router(state: AgentState):
    """
    Resume into the correct internal node based on `state.waiting_for`.
    """
    if state.waiting_for == AgentState.WaitingFor.PROBLEM_CONFIRMATION:
        return "parse_problem_confirmation"
    # Default (including PROBLEM_INPUT and first entry)
    return "deactive_current_context"

graph = StateGraph(AgentState)

graph.add_node("problem_entry_router", lambda s: s)
add_safe_node(graph, "deactive_current_context", deactive_current_context)
add_safe_node(graph, "extract_problem", extract_problem_node)
add_safe_node(graph, "parse_problem_confirmation", parse_confirmation_node)
add_safe_node(graph, "create_new_problem_instance", create_new_problem_instance_node)

graph.set_entry_point("problem_entry_router")
graph.add_conditional_edges(
    "problem_entry_router",
    problem_entry_router,
    {
        "deactive_current_context": "deactive_current_context",
        "parse_problem_confirmation": "parse_problem_confirmation",
    }
)

graph.add_edge("deactive_current_context", "extract_problem")

problem_subgraph = graph.compile()
