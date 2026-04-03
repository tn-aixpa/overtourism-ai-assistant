from langgraph.graph import StateGraph

from app.agent.state import AgentState
from app.agent.graphs.utils import add_safe_node
from app.agent.nodes.proposal import (
    extract_proposal,
    parse_proposal_confirmation,
    assert_active_problem,
    create_proposal
)


def proposal_entry_router(state: AgentState):
    """
    Resume into the correct internal node based on `state.waiting_for`.
    """
    if state.waiting_for == AgentState.WaitingFor.PROPOSAL_CONFIRMATION:
        return "parse_proposal_confirmation"
    # Default (including PROPOSAL_INPUT and first entry)
    return "assert_active_problem"

# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("proposal_entry_router", lambda s: s)
add_safe_node(graph, "assert_active_problem", assert_active_problem)
add_safe_node(graph, "extract_proposal", extract_proposal)
add_safe_node(graph, "parse_proposal_confirmation", parse_proposal_confirmation)
add_safe_node(graph, "create_proposal", create_proposal)

graph.set_entry_point("proposal_entry_router")

graph.add_conditional_edges(
    "proposal_entry_router",
    proposal_entry_router,
    {
        "parse_proposal_confirmation": "parse_proposal_confirmation",
        "assert_active_problem": "assert_active_problem",
    }
)

new_proposal_subgraph = graph.compile()
