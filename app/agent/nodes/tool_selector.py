"""
Tool selection node for the agentic system.

Uses LLM reasoning to select which tool the agent should execute based on user input.
"""

import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.agent_tools import get_all_agent_tools
from app.prompts.tool_selection import select_tools

logger = logging.getLogger(__name__)


def initialize_tools(state: AgentState) -> Command:
    """
    Initialize available tools and route to tool_selector.

    Entry point for both standard and integrated modes.
    If a confirmation flow is in progress, resumes it directly.
    """
    logger.info("Initializing available tools")

    if state.waiting_for and state.user_input:
        logger.info(
            f"Resuming from waiting_for={state.waiting_for}, routing to WAIT_USER_INPUT"
        )
        return Command(update=state, goto="WAIT_USER_INPUT")

    registry = get_tool_registry()
    if not registry.list_tool_names():
        logger.info("Registering default agent tools")
        registry.register_tools(get_all_agent_tools())

    allowlist = state.cognitive.known_tools or None
    known_tools = registry.get_context_tools(allowlist=allowlist)
    state.cognitive.known_tools = list(known_tools.keys())

    # In non-integrated mode enabled_tools is not pre-set by the route, so
    # make all known tools available. In integrated mode the route already
    # wrote the restricted allowlist and we must not overwrite it.
    if not state.integrated_mode:
        state.cognitive.enabled_tools = state.cognitive.known_tools

    logger.info(f"Available tools: {state.cognitive.enabled_tools}")
    return Command(update=state, goto="tool_selector")


def tool_selector_node(state: AgentState) -> Command:
    logger.info("Entering tool selector node")

    registry = get_tool_registry()
    tools_for_llm = registry.get_tools_for_llm(allowlist=None)
    tools_for_llm_enabled = registry.get_tools_for_llm(
        allowlist=state.cognitive.enabled_tools
    )

    if not tools_for_llm:
        logger.warning("No tools available for this context")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.tool_plan = []
        state.cognitive.tool_plan_index = 0
        state.cognitive.current_plan_result_keys = []
        return Command(update=state, goto="generate_output_message")

    import json
    import re

    try:
        raw = select_tools(state, tools_for_llm, tools_for_llm_enabled)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        response_json = json.loads(raw)
    except Exception as e:
        logger.exception("Error parsing tool selection response")
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")

    action = response_json.get("action")

    if action == "clarify":
        state.cognitive.messages_to_include = [
            response_json.get("message", "Could you clarify your request?")
        ]
        return Command(update=state, goto="generate_output_message")

    if action == "tool_unavailable":
        state.cognitive.messages_to_include = [
            response_json.get(
                "message",
                "The current request cannot be handle in the current context. Please change contex or use the standalone chat.",
            )
        ]
        return Command(update=state, goto="generate_output_message")

    if action == "out_of_scope":
        state.cognitive.messages_to_include = [
            response_json.get("message", "That request is outside my scope.")
        ]
        return Command(update=state, goto="generate_output_message")

    enabled_tool_names = {t["function"]["name"] for t in tools_for_llm_enabled}

    if "tool_plan" in response_json:
        raw_plan = response_json["tool_plan"]
    elif response_json.get("tool_name"):
        raw_plan = [
            {
                "tool_name": response_json["tool_name"],
                "arguments": response_json.get("arguments", {}),
            }
        ]
    else:
        raw_plan = []

    tool_plan = [
        {"tool_name": step["tool_name"], "arguments": step.get("arguments", {})}
        for step in raw_plan
        if step.get("tool_name") and step["tool_name"] in enabled_tool_names
    ]

    for step in raw_plan:
        if step.get("tool_name") and step["tool_name"] not in enabled_tool_names:
            logger.warning(
                f"LLM planned unavailable tool '{step['tool_name']}', skipping"
            )

    state.cognitive.tool_plan = tool_plan
    state.cognitive.tool_plan_index = 0
    state.cognitive.current_plan_result_keys = []

    if tool_plan:
        state.cognitive.selected_tool = tool_plan[0]["tool_name"]
        state.cognitive.tool_arguments = tool_plan[0]["arguments"]
    else:
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}

    state.add_trace(
        "tool_selection",
        "tool_selector",
        {"tool_plan": tool_plan, "known_tools": list(enabled_tool_names)},
    )

    logger.info(f"Tool plan: {tool_plan}")

    if tool_plan:
        return Command(update=state, goto="tool_executor")
    return Command(update=state, goto="generate_output_message")
