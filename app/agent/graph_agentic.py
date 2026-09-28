"""
ReAct graph for the digital twin agent.

Graph flow (Thought -> Action -> Observation, repeated):
1. initialize_tools     — determine available tools; reset the scratchpad for a new turn
                           (or resume a pending confirmation/clarification directly)
2. top_level_router      — resolve which domain (system info / location tools /
                           region-wide indexes / general question) this turn belongs
                           to, scope the tool list to it, or pause at WAIT_USER_INPUT
                           to ask the user which domain they mean
3. react_reasoner        — ONE reasoning step: decide the next tool call, or finish
4. tool_executor         — Act: run the selected tool, record the Observation, loop back
                           to react_reasoner (or pause at WAIT_USER_INPUT for confirmation)
5. WAIT_USER_INPUT       — pause the loop for mutating tools / tier consent / topic
                           routing until the user replies
6. generate_output_message — synthesize the final response to the user
"""

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.nodes.reasoner import initialize_tools, react_reasoner_node
from app.agent.nodes.router import top_level_router_node
from app.agent.nodes.tool_executor import tool_executor_node
from app.agent.nodes.general import add_safe_node, error_recovery_node, generate_output_message_node
from app.agent.nodes.waiting import wait_user_input_node


def build_agentic_graph():
    """Build the ReAct graph."""
    graph = StateGraph(AgentState)

    add_safe_node(graph, "initialize_tools", initialize_tools)
    add_safe_node(graph, "top_level_router", top_level_router_node)
    add_safe_node(graph, "react_reasoner", react_reasoner_node)
    add_safe_node(graph, "tool_executor", tool_executor_node)
    add_safe_node(graph, "error", error_recovery_node)
    add_safe_node(graph, "WAIT_USER_INPUT", wait_user_input_node)
    add_safe_node(graph, "generate_output_message", generate_output_message_node)

    graph.set_entry_point("initialize_tools")
    # NOTE: initialize_tools always returns an explicit Command(goto=...) to
    # either "top_level_router" or "WAIT_USER_INPUT". top_level_router in
    # turn always returns an explicit Command(goto=...) to either
    # "react_reasoner" or "WAIT_USER_INPUT". Do NOT also add static edges
    # for either of these here: a static edge plus a Command-based goto
    # fire in the same superstep and both write to the full state, which
    # raises "Can receive only one value per step" once the WAIT_USER_INPUT
    # resume path is taken.
    #
    # Likewise react_reasoner <-> tool_executor form the Thought/Action/
    # Observation loop entirely via Command(goto=...) — react_reasoner picks
    # "tool_executor" or "generate_output_message", tool_executor picks
    # "react_reasoner", "WAIT_USER_INPUT", or "error" depending on the
    # outcome of the action it just ran. No static edges between them.
    graph.add_edge("error", "generate_output_message")
    graph.add_edge("generate_output_message", END)

    return graph.compile()


app = build_agentic_graph()
