from langgraph.graph import StateGraph

from app.agent.state import AgentState
from app.agent.graphs.utils import add_safe_node
from app.agent.nodes.intent import intent_node, validate_intent_node, route_from_intent

# ---- Build subgraph

graph = StateGraph(AgentState)

add_safe_node(graph, "assess_intent", intent_node)
add_safe_node(graph, "validate_intent", validate_intent_node)
add_safe_node(graph, "route_intent", route_from_intent)

graph.set_entry_point("assess_intent")

graph.add_edge("assess_intent", "validate_intent")
graph.add_edge("validate_intent", "route_intent")

intent_subgraph = graph.compile()

