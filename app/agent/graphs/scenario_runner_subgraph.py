from langgraph.graph import StateGraph

from app.agent.nodes.scenario import run_scenario_node
from app.agent.graphs.utils import add_safe_node
from app.agent.state import AgentState

graph = StateGraph(AgentState)

add_safe_node(graph, "run_scenario", run_scenario_node)

graph.set_entry_point("run_scenario")

scenario_runner_subgraph = graph.compile()