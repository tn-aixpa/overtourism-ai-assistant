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

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from app.agent.state import AgentState
from app.agent.nodes.tool_selector import initialize_tools, tool_selector_node
from app.agent.nodes.tool_executor import tool_executor_node
from app.agent.nodes.general import error_recovery_node, generate_output_message_node
from app.agent.nodes.waiting import wait_user_input_node, resume_router
from app.agent.graphs.utils import add_safe_node


def build_agentic_graph():
    """Build the new simplified agentic graph."""
    
    graph = StateGraph(AgentState)
    
    # Add nodes
    add_safe_node(graph, "initialize_tools", initialize_tools)
    add_safe_node(graph, "tool_selector", tool_selector_node)
    add_safe_node(graph, "tool_executor", tool_executor_node)
    add_safe_node(graph, "error", error_recovery_node)
    add_safe_node(graph, "WAIT_USER_INPUT", wait_user_input_node)
    add_safe_node(graph, "resume_router", lambda s: s)  # passthrough
    add_safe_node(graph, "generate_output_message", generate_output_message_node)
    
    # Entry point
    graph.set_entry_point("resume_router")
    
    # Edge from resume router
    graph.add_conditional_edges(
        "resume_router",
        resume_router,
        {
            "initialize_tools": "initialize_tools",
            "WAIT_USER_INPUT": "WAIT_USER_INPUT",
        }
    )
    
    # Main flow: tools -> selector -> executor -> output
    graph.add_edge("initialize_tools", "tool_selector")
    graph.add_edge("tool_selector", "tool_executor")
    
    # Tool executor can go to wait, output, or error
    # (These are determined inside tool_executor_node via Command)
    # But we need conditional edges for the control flow
    
    # Error recovery goes to output
    graph.add_edge("error", "generate_output_message")
    
    # Output goes to END
    graph.add_edge("generate_output_message", END)
    
    # Wait for input goes back to resume router
    graph.add_edge("WAIT_USER_INPUT", "resume_router")
    
    return graph.compile()


# Compile the main app
app = build_agentic_graph()
