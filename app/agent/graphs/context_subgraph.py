from langgraph.graph import StateGraph

from app.agent.nodes.context_management import assess_context_request, handle_context, routing_after_context
from app.agent.state import AgentState
from app.agent.graphs.utils import add_safe_node

# ---- Build subgraph

graph = StateGraph(AgentState)

add_safe_node(graph, "assess_context_request", assess_context_request)
add_safe_node(graph, "handle_context", handle_context)
add_safe_node(graph, "routing_after_context", routing_after_context)

graph.set_entry_point("assess_context_request")

graph.add_edge("assess_context_request", "handle_context")
graph.add_edge("handle_context", "routing_after_context")

context_subgraph = graph.compile()
