from langgraph.graph import StateGraph

from app.agent.state import AgentState
from app.agent.graphs import (
    intent_subgraph,
    interaction_subgraph,
    problem_subgraph,
    scenario_extraction_subgraph,
    scenario_runner_subgraph,
    list_available_subgraph,
    context_subgraph
)
from app.agent.nodes.error_recovery import error_recovery_node
from app.agent.nodes.waiting import wait_user_input_node, resume_router

graph = StateGraph(AgentState)

graph.add_node("resume_router", lambda s: s)  # passthrough
graph.add_node("WAIT_USER_INPUT", wait_user_input_node)
graph.add_node("context_management", context_subgraph)
graph.add_node("intent", intent_subgraph)
graph.add_node("list_available", list_available_subgraph)
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
        "WAIT_USER_INPUT": "WAIT_USER_INPUT",
    }
)
graph.set_entry_point("resume_router")
app = graph.compile()
