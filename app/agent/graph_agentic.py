"""
Agentic graph for the digital twin agent.

This is the refactored graph structure that uses tool-based decision making
instead of hardcoded workflow routing.

Graph flow:
1. Initialize tools (determine which tools are available)
2. Select tool (LLM decides which tool to call)
3. Execute tool (run the selected tool)
4. Handle result (confirmation, error handling, etc.)
5. Generate output (format response to user)

This graph is much simpler and more extensible than the original workflow-based design.
"""

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.nodes.tool_selector import initialize_tools, inject_tools_node, tool_selector_node
from app.agent.nodes.tool_executor import tool_executor_node
from app.agent.nodes.general import error_recovery_node, generate_output_message_node
from app.agent.nodes.waiting import wait_user_input_node
from app.agent.graphs.utils import add_safe_node


def build_agentic_graph():
    """Build the simplified agentic graph."""

    graph = StateGraph(AgentState)

    add_safe_node(graph, "initialize_tools", initialize_tools)
    add_safe_node(graph, "inject_tools", inject_tools_node)
    add_safe_node(graph, "tool_selector", tool_selector_node)
    add_safe_node(graph, "tool_executor", tool_executor_node)
    add_safe_node(graph, "error", error_recovery_node)
    add_safe_node(graph, "WAIT_USER_INPUT", wait_user_input_node)
    add_safe_node(graph, "generate_output_message", generate_output_message_node)

    # Entry point for standard mode
    graph.set_entry_point("initialize_tools")

    # initialize_tools and inject_tools both proceed to tool_selector
    graph.add_edge("initialize_tools", "tool_selector")
    graph.add_edge("inject_tools", "tool_selector")

    # tool_selector routes via Command to:
    #   tool_executor           (tool selected)
    #   generate_output_message (no tool needed — conversational reply)
    #   error                   (parse failure)
    # No static edge from tool_selector: all routing is Command-based.

    # tool_executor routes via Command to:
    #   generate_output_message | WAIT_USER_INPUT | error
    graph.add_edge("error", "generate_output_message")
    graph.add_edge("generate_output_message", END)

    # WAIT_USER_INPUT routes via Command to:
    #   generate_output_message (first pass — emit prompt, then END)
    #   tool_executor           (user confirmed)
    #   generate_output_message (user cancelled)
    #   initialize_tools        (ambiguous reply — re-interpret)
    # No static edge from WAIT_USER_INPUT: all routing is Command-based.

    return graph.compile()


# Compile the main app
app = build_agentic_graph()
