"""
Agentic graph for the digital twin agent.

Graph flow:
1. Initialize tools (determine which tools are available)
2. Select tool plan (LLM decides which tools to call in order)
3. Execute tool plan (executor iterates through plan, looping back to itself)
4. Handle result (confirmation, error handling, etc.)
5. Generate output (format response to user)
"""

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.nodes.tool_selector import initialize_tools, tool_selector_node
from app.agent.nodes.tool_executor import tool_executor_node
from app.agent.nodes.general import add_safe_node, error_recovery_node, generate_output_message_node
from app.agent.nodes.waiting import wait_user_input_node


def build_agentic_graph():
    """Build the agentic graph."""
    graph = StateGraph(AgentState)

    add_safe_node(graph, "initialize_tools", initialize_tools)
    add_safe_node(graph, "tool_selector", tool_selector_node)
    add_safe_node(graph, "tool_executor", tool_executor_node)
    add_safe_node(graph, "error", error_recovery_node)
    add_safe_node(graph, "WAIT_USER_INPUT", wait_user_input_node)
    add_safe_node(graph, "generate_output_message", generate_output_message_node)

    graph.set_entry_point("initialize_tools")
    graph.add_edge("initialize_tools", "tool_selector")
    graph.add_edge("error", "generate_output_message")
    graph.add_edge("generate_output_message", END)

    return graph.compile()


app = build_agentic_graph()
