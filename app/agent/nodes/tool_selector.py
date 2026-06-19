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
from app.agent.events import publish

logger = logging.getLogger(__name__)


def initialize_tools(state: AgentState) -> Command:
    """
    Initialize available tools based on user context and access control.

    This node is the graph entry point for standard mode. If the session is
    waiting for user input (e.g. a confirmation), route directly to
    WAIT_USER_INPUT instead of re-running tool selection.
    """
    logger.info("Initializing available tools")
    publish(state.session_id, "Analyzing your request...")

    # Resume a suspended confirmation flow without re-running tool selection.
    if state.waiting_for and state.user_input:
        logger.info(f"Resuming from waiting_for={state.waiting_for}, routing to WAIT_USER_INPUT")
        return Command(update=state, goto="WAIT_USER_INPUT")

    # Register tools if not already done
    registry = get_tool_registry()
    if not registry.list_tool_names():
        logger.info("Registering default agent tools")
        all_tools = get_all_agent_tools()
        registry.register_tools(all_tools)
   
    # Get tools available in this context
    available_tools = registry.get_context_tools(
        active_context=state.cognitive.active_context_type or None,
    )
    
    state.cognitive.available_tools = list(available_tools.keys())
    
    logger.info(f"Available tools: {state.cognitive.available_tools}")
    
    return Command(update=state, goto="tool_selector")


def tool_selector_node(state: AgentState) -> Command:
    logger.info("Entering tool selector node")
    publish(state.session_id, "Determining next action...")

    registry = get_tool_registry()

    tools_for_llm = registry.get_tools_for_llm(
        active_context=state.cognitive.active_context_type or None,
    )

    if not tools_for_llm:
        logger.warning("No tools available for this context")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.tool_plan = []
        state.cognitive.tool_plan_index = 0
        return Command(update=state, goto="generate_output_message")

    import json
    import re
    from app.utils.llm import llm_interaction, format_messages

    message = (state.get_last_user_message() or "").content
    history = state.get_reasoning_context()
    history_block = format_messages(history) if history else "None"
    active_context = state.get_active_context_string() or "None"
    tools_json = json.dumps(tools_for_llm, indent=2)

    # Summarise previously collected tool results so the LLM can use them
    prior_results_block = "None"
    if state.cognitive.tool_results:
        prior_results_block = json.dumps(state.cognitive.tool_results, indent=2, default=str)

    prompt = f"""
You are an assistant for a digital twin platform named AIxPA related to tourism management.

You may return ONE of the following JSON objects:

Tool plan (one OR more tools to run in sequence):
{{
  "tool_plan": [
    {{"tool_name": "<tool name>", "arguments": {{}}}},
    {{"tool_name": "<tool name>", "arguments": {{}}}}
  ]
}}

Single tool (shorthand, also valid):
{{
  "tool_name": "<tool name>",
  "arguments": {{}}
}}

Clarification:
{{
  "action": "clarify",
  "message": "..."
}}

Out of scope:
{{
  "action": "out_of_scope",
  "message": "..."
}}

No action needed:
{{
  "tool_name": null,
  "arguments": {{}}
}}

IMPORTANT – when the user asks for something that requires multiple steps (e.g. "list problems AND proposals",
or "show me details of a specific scenario" which first requires listing scenarios to find the right id),
use a tool_plan with the full ordered sequence of tools needed to fulfil the request.

Previously collected tool results (available for argument resolution):
{prior_results_block}

Active context: {active_context}

Conversation so far:
{history_block}

New user message:
"{message}"

Available tools:
{tools_json}

Return ONLY valid JSON.
"""

    try:
        raw = llm_interaction(state, prompt).strip()

        raw = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            raw,
            flags=re.MULTILINE,
        ).strip()

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

    if action == "out_of_scope":
        state.cognitive.messages_to_include = [
            response_json.get("message", "That request is outside my scope.")
        ]
        return Command(update=state, goto="generate_output_message")

    available_tool_names = {
        t.get("function", {}).get("name")
        for t in tools_for_llm
        if t.get("function", {}).get("name")
    }

    # ---- Normalise response into a tool_plan list ----
    if "tool_plan" in response_json:
        raw_plan = response_json["tool_plan"]
    elif response_json.get("tool_name"):
        raw_plan = [{"tool_name": response_json["tool_name"], "arguments": response_json.get("arguments", {})}]
    else:
        raw_plan = []

    # Validate each step against available tools
    tool_plan = []
    for step in raw_plan:
        tool_name = step.get("tool_name")
        if tool_name and tool_name in available_tool_names:
            tool_plan.append({"tool_name": tool_name, "arguments": step.get("arguments", {})})
        elif tool_name:
            logger.warning(f"LLM planned unavailable tool '{tool_name}', skipping")

    state.cognitive.tool_plan = tool_plan
    state.cognitive.tool_plan_index = 0
    # Convenience aliases kept in sync with first step for backwards compat
    if tool_plan:
        state.cognitive.selected_tool = tool_plan[0]["tool_name"]
        state.cognitive.tool_arguments = tool_plan[0]["arguments"]
    else:
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}

    state.add_trace(
        "tool_selection",
        "tool_selector",
        {
            "tool_plan": tool_plan,
            "available_tools": list(available_tool_names),
        },
    )

    logger.info(f"Tool plan: {tool_plan}")

    if tool_plan:
        return Command(update=state, goto="tool_executor")

    return Command(update=state, goto="generate_output_message")
    
def inject_tools_node(state: AgentState) -> Command:
    """
    Integrated-mode fast path: inject tools filtered by active_context_type,
    skipping the full initialize_tools registration flow.

    Expects state.cognitive.active_context_type to already be set by the API
    layer before the graph is invoked.

    Also handles resuming a suspended confirmation flow in integrated mode.
    """
    logger.info(
        "Injecting tools for integrated mode "
        f"(context_type={state.cognitive.active_context_type})"
    )
    publish(state.session_id, "Analyzing your request...")

    # Resume a suspended confirmation flow without re-running tool selection.
    if state.waiting_for and state.user_input:
        logger.info(f"Resuming from waiting_for={state.waiting_for}, routing to WAIT_USER_INPUT")
        return Command(update=state, goto="WAIT_USER_INPUT")

    registry = get_tool_registry()

    # Ensure tools are registered (idempotent)
    if not registry.list_tool_names():
        logger.info("Registering default agent tools")
        all_tools = get_all_agent_tools()
        registry.register_tools(all_tools)

    available_tools = registry.get_context_tools(
        active_context=state.cognitive.active_context_type or None,
    )

    # In integrated mode the embedding application already provides context, so
    # high-level discovery tools add noise rather than value. Exclude
    # get_system_capabilities whenever an active context type is already set.
    if state.integrated_mode and state.cognitive.active_context_type:
        available_tools = {
            name: tool
            for name, tool in available_tools.items()
            if name != "get_system_capabilities"
        }
        logger.info("Integrated mode: excluded get_system_capabilities (context already set)")

    state.cognitive.available_tools = list(available_tools.keys())
    logger.info(f"Injected tools for integrated mode: {state.cognitive.available_tools}")

    return Command(update=state, goto="tool_selector")
