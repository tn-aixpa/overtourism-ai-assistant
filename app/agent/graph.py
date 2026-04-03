from langgraph.graph import StateGraph

from app.agent.state import AgentState
from app.agent.graphs import (
    intent_subgraph,
    interaction_subgraph,
    new_problem_subgraph,
    new_proposal_subgraph,
    new_scenario_subgraph,
    list_available_subgraph,
    context_subgraph
)
from app.agent.nodes.general import error_recovery_node, generate_output_message_node, temp_node
from app.agent.nodes.waiting import wait_user_input_node, resume_router

graph = StateGraph(AgentState)

graph.add_node("resume_router", lambda s: s)  # passthrough
graph.add_node("WAIT_USER_INPUT", wait_user_input_node)
graph.add_node("context_management", context_subgraph)
graph.add_node("intent", intent_subgraph)
graph.add_node("list_available", list_available_subgraph)
graph.add_node("interaction", interaction_subgraph)
graph.add_node("new_problem", new_problem_subgraph)
graph.add_node("new_proposal", new_proposal_subgraph)
graph.add_node("new_scenario", new_scenario_subgraph)
graph.add_node("error", error_recovery_node )
graph.add_node("generate_output_message", generate_output_message_node)
graph.add_node("temp_node", temp_node)

graph.add_conditional_edges(
    "resume_router",
    resume_router,
    {
        "intent": "intent",
        "WAIT_USER_INPUT": "WAIT_USER_INPUT",
    }
)
graph.set_entry_point("temp_node")
app = graph.compile()
