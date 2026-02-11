from langgraph.graph import StateGraph

from .nodes.error_recovery import error_recovery_node
from .state import AgentState
from .graphs import intent_subgraph, interaction_subgraph, problem_subgraph, scenario_extraction_subgraph, scenario_runner_subgraph

# ─────────────────────────────────────────────
# Graph definition
# ─────────────────────────────────────────────

graph = StateGraph(AgentState)

graph.add_node("intent", intent_subgraph)
graph.add_node("interaction", interaction_subgraph)
graph.add_node("problem", problem_subgraph)
graph.add_node("scenario_extraction", scenario_extraction_subgraph)
graph.add_node("scenario_runner", scenario_runner_subgraph)
graph.add_node("error", error_recovery_node )

graph.set_entry_point("intent")

app = graph.compile()