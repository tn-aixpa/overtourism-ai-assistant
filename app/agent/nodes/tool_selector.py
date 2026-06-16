"""
Tool selection node for the agentic system.

Uses LLM reasoning to select which tool the agent should execute based on user input.
This is the core of the agentic decision-making.
"""

import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.agent_tools import get_all_agent_tools
from app.utils.llm_reasoning import extract_action_plan
from app.agent.events import publish

logger = logging.getLogger(__name__)


def initialize_tools(state: AgentState) -> Command:
    """
    Initialize available tools based on user context and access control.
    
    This node runs early to populate available tools that the agent can choose from.
    """
    logger.info("Initializing available tools")
    publish(state.session_id, "Analyzing your request...")
    
    # Register tools if not already done
    registry = get_tool_registry()
    if not registry.list_tool_names():
        logger.info("Registering default agent tools")
        all_tools = get_all_agent_tools()
        registry.register_tools(all_tools)
    
    # Get tools available to this user and context
    available_tools = registry.get_context_tools(
        user_id=state.user_id,
        active_context=state.cognitive.active_context_type or None,
    )
    
    state.cognitive.available_tools = list(available_tools.keys())
    
    logger.info(f"Available tools for user {state.user_id}: {state.cognitive.available_tools}")
    
    return Command(update=state, goto="tool_selector")


def tool_selector_node(state: AgentState) -> Command:
    """
    Use LLM reasoning to select which tool to execute.
    
    The LLM analyzes:
    1. The user's intent
    2. Available tools and their descriptions
    3. Current context
    4. State history
    
    Then decides which tool to call (or if conversation is sufficient).
    """
    logger.info("Entering tool selector node")
    publish(state.session_id, "Determining next action...")
    
    registry = get_tool_registry()
    
    # Get available tools formatted for LLM
    tools_for_llm = registry.get_tools_for_llm(
        user_id=state.user_id,
        active_context=state.cognitive.active_context_type or None,
    )
    
    # If no tools available, go to output
    if not tools_for_llm:
        logger.warning("No tools available for this context")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        return Command(update=state, goto="generate_output_message")
    
    # Prepare prompt for tool selection
    tool_descriptions = registry.get_tools_description(
        user_id=state.user_id,
        active_context=state.cognitive.active_context_type or None,
    )
    
    # Use existing LLM reasoning to extract action plan
    # This could be enhanced to use tool_choice='required' if available
    try:
        plan = extract_action_plan(state)
        selected_tool = plan[0] if plan else None
    except Exception as e:
        logger.error(f"Error in tool selection: {e}")
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")
    
    # Validate that selected tool is available
    if selected_tool and selected_tool not in state.cognitive.available_tools:
        logger.warning(f"LLM selected tool '{selected_tool}' but it's not available")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        return Command(update=state, goto="generate_output_message")
    
    state.cognitive.selected_tool = selected_tool
    state.add_trace("tool_selection", "tool_selector", {
        "selected_tool": selected_tool,
        "available_tools": state.cognitive.available_tools,
    })
    
    logger.info(f"Selected tool: {selected_tool}")
    
    if selected_tool:
        return Command(update=state, goto="tool_executor")
    else:
        return Command(update=state, goto="generate_output_message")


def tool_router(state: AgentState) -> str:
    """
    Route based on whether a tool was selected.
    """
    if state.cognitive.selected_tool:
        return "tool_executor"
    else:
        return "generate_output_message"
