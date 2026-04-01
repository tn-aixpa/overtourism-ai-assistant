from langgraph.graph import StateGraph
import logging

from app.agent.state import AgentState
from app.agent.nodes.iteraction import assert_active_context, select_role, interact_context
from app.agent.graphs.utils import add_safe_node

logger = logging.getLogger(__name__)

# ---- Build subgraph

graph = StateGraph(AgentState)

add_safe_node(graph, "assert_active_context", assert_active_context)
add_safe_node(graph, "select_role", select_role)
add_safe_node(graph, "interact_context", interact_context)

graph.set_entry_point("select_role")

graph.add_edge("select_role", "interact_context")

interaction_subgraph = graph.compile()
