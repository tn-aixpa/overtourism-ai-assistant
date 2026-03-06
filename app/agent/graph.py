from langgraph.graph import StateGraph

from .nodes.error_recovery import error_recovery_node
from .state import AgentState
from .graphs import intent_subgraph, interaction_subgraph, problem_subgraph, scenario_extraction_subgraph, scenario_runner_subgraph

# ─────────────────────────────────────────────
# Graph definition
# ─────────────────────────────────────────────
def resume_router(state: AgentState):
    if state.last_node and state.last_node.startswith("WAIT_"):
        return state.last_node  # jump to the right node
    return "intent"

graph = StateGraph(AgentState)

graph.add_node("resume_router", lambda s: s)  # passthrough
graph.add_node("intent", intent_subgraph)
graph.add_node("interaction", interaction_subgraph)
graph.add_node("problem", problem_subgraph)
graph.add_node("scenario_extraction", scenario_extraction_subgraph)
graph.add_node("scenario_runner", scenario_runner_subgraph)
graph.add_node("error", error_recovery_node )

graph.add_conditional_edges(
    "resume_router",
    resume_router,
    {
        "intent": "intent",
        "WAIT_PROBLEM_INPUT": "problem",
        "WAIT_CONFIRMATION_PROBLEM": "problem",
        "WAIT_SCENARIO_PREFERENCE": "problem",
        "WAIT_CONFIRMATION_SCENARIO": "scenario_extraction",
        "WAIT_SCENARIO_INPUT": "scenario_extraction"
    }
)
graph.set_entry_point("resume_router")
app = graph.compile()
