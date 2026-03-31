from langgraph.graph import StateGraph, END

from app.agent.graphs.utils import add_safe_node
from app.agent.state import AgentState
from app.agent.nodes.listing import assess_list, get_list, generate_answer

graph = StateGraph(AgentState)

add_safe_node(graph, "assess_list", assess_list)
add_safe_node(graph, "get_list", get_list)
add_safe_node(graph, "generate_answer", generate_answer)

graph.add_edge("assess_list", "get_list")
graph.add_edge("get_list", "generate_answer")


graph.set_entry_point("assess_list")

list_available_subgraph = graph.compile()