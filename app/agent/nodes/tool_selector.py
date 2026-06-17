"""
Tool selection node for the agentic system.

Uses LLM reasoning to select which tool the agent should execute based on user input.
This is the core of the agentic decision-making.
"""

import logging
from langgraph.types import Command
import re

from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.agent_tools import get_all_agent_tools
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
   
    # Get tools available in this context
    # Note: user_id=None grants all tools. In future, pass specific user_id to restrict.
    available_tools = registry.get_context_tools(
        user_id=None,
        active_context=state.cognitive.active_context_type or None,
    )
    
    state.cognitive.available_tools = list(available_tools.keys())
    
    logger.info(f"Available tools: {state.cognitive.available_tools}")
    
    return Command(update=state, goto="tool_selector")


def tool_selector_node(state: AgentState) -> Command:
    """
    Use LLM reasoning to select which tool to execute and extract its arguments.

    The LLM receives:
    1. The user's message and conversation history
    2. Available tools with their descriptions and parameters
    3. Current active context

    Then selects a tool and extracts the required arguments.
    """
    logger.info("Entering tool selector node")
    publish(state.session_id, "Determining next action...")

    registry = get_tool_registry()

    # Get available tools for the current context
    tools_for_llm = registry.get_tools_for_llm(
        user_id=None,
        active_context=state.cognitive.active_context_type or None,
    )

    if not tools_for_llm:
        logger.warning("No tools available for this context")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        return Command(update=state, goto="generate_output_message")

    # Build prompt
    import json
    from app.utils.llm import llm_interaction, format_messages

    message = (state.get_last_user_message() or "").content
    history = state.get_reasoning_context()
    history_block = format_messages(history) if history else "None"
    active_context = state.get_active_context_string() or "None"
    tools_json = json.dumps(tools_for_llm, indent=2)

    prompt = f"""You are a tool selector for a digital-twin assistant about city management and overtourism.

Active context: {active_context}

Conversation so far:
{history_block}

New user message: "{message}"

Available tools:
{tools_json}

Your task:
1. Select the single most appropriate tool to handle the user's request.
2. Extract all required (and relevant optional) arguments for that tool from the user message and conversation history.
3. If no tool is needed (e.g. simple conversational reply), return null for the tool name.

Return ONLY a JSON object in this exact format, no explanation, no markdown fences:
{{
  "tool_name": "<tool name or null>",
  "arguments": {{
    "<param_name>": "<param_value>"
  }}
}}

Rules:
- tool_name must be one of the available tool names, or null.
- arguments must match the tool's parameter definitions exactly.
- For extract_* tools, pass the full user message as user_input.
- If the user is just greeting or asking a general question, return null.
- Never invent tool names not in the list.
"""

    try:
        raw = llm_interaction(state, prompt).strip()
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)

        selected_tool = parsed.get("tool_name")
        tool_arguments = parsed.get("arguments", {})

    except Exception as e:
        logger.error(f"Error parsing tool selection response: {e}")
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")

    logger.info(f"Selected tools: {tools_for_llm}")
    # Validate selected tool is actually available in this context
    available_tool_names = {t["function"]["name"] for t in tools_for_llm}
    if selected_tool and selected_tool not in available_tool_names:
        logger.warning(f"LLM selected tool '{selected_tool}' not available in current context")
        selected_tool = None
        tool_arguments = {}

    state.cognitive.selected_tool = selected_tool
    state.cognitive.tool_arguments = tool_arguments or {}
    state.add_trace("tool_selection", "tool_selector", {
        "selected_tool": selected_tool,
        "tool_arguments": tool_arguments,
        "available_tools": list(available_tool_names),
    })

    logger.info(f"Selected tool: {selected_tool} with args: {tool_arguments}")

    if selected_tool:
        return Command(update=state, goto="tool_executor")
    else:
        return Command(update=state, goto="generate_output_message")
    
def inject_tools_node(state: AgentState) -> Command:
    """
    Integrated-mode fast path: inject tools filtered by active_context_type,
    skipping the full initialize_tools registration flow.

    Expects state.cognitive.active_context_type to already be set by the API
    layer before the graph is invoked.
    """
    logger.info(
        "Injecting tools for integrated mode "
        f"(context_type={state.cognitive.active_context_type})"
    )
    publish(state.session_id, "Analyzing your request...")

    registry = get_tool_registry()

    # Ensure tools are registered (idempotent)
    if not registry.list_tool_names():
        logger.info("Registering default agent tools")
        all_tools = get_all_agent_tools()
        registry.register_tools(all_tools)

    available_tools = registry.get_context_tools(
        user_id=None,
        active_context=state.cognitive.active_context_type or None,
    )

    state.cognitive.available_tools = list(available_tools.keys())
    logger.info(f"Injected tools for integrated mode: {state.cognitive.available_tools}")

    return Command(update=state, goto="tool_selector")


# def tool_router(state: AgentState) -> str:
#     """
#     Route based on whether a tool was selected.
#     """
#     if state.cognitive.selected_tool:
#         return "tool_executor"
#     else:
#         return "generate_output_message"
