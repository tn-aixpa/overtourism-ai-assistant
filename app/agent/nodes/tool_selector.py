"""
Tool selection node for the agentic system.

Uses LLM reasoning to select which tool the agent should execute based on user input.
"""

import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.agent_tools import get_all_agent_tools

logger = logging.getLogger(__name__)


def initialize_tools(state: AgentState) -> Command:
    """
    Initialize available tools and route to tool_selector.

    Entry point for both standard and integrated modes.
    If a confirmation flow is in progress, resumes it directly.
    """
    logger.info("Initializing available tools")

    if state.waiting_for and state.user_input:
        logger.info(f"Resuming from waiting_for={state.waiting_for}, routing to WAIT_USER_INPUT")
        return Command(update=state, goto="WAIT_USER_INPUT")

    registry = get_tool_registry()
    if not registry.list_tool_names():
        logger.info("Registering default agent tools")
        registry.register_tools(get_all_agent_tools())

    allowlist = state.cognitive.available_tools or None
    available_tools = registry.get_context_tools(allowlist=allowlist)
    state.cognitive.available_tools = list(available_tools.keys())

    logger.info(f"Available tools: {state.cognitive.available_tools}")
    return Command(update=state, goto="tool_selector")


def tool_selector_node(state: AgentState) -> Command:
    logger.info("Entering tool selector node")

    registry = get_tool_registry()
    allowlist = state.cognitive.available_tools or None
    tools_for_llm = registry.get_tools_for_llm(allowlist=allowlist)

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
    tools_json = json.dumps(tools_for_llm, indent=2)

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

No action needed (greetings, thanks, chitchat):
{{
  "tool_name": null,
  "arguments": {{}}
}}

## Tool selection rules — follow in order

RULE 1 – GREETINGS AND GENERAL QUESTIONS:
If the user message is a greeting (e.g. "Ciao", "Hello", "Hi"), a thank-you, or a general
question about what the system can do, return:
  {{"tool_name": "get_system_capabilities", "arguments": {{}}}}
Do NOT call get_context_details or interact_with_context for greetings or general questions.

RULE 2 – CONTEXT TOOLS REQUIRE ACTUAL DATA:
Only use get_context_details or interact_with_context when the user is explicitly asking
about specific problems, proposals, or scenarios that exist in the system.
Do NOT use these tools for greetings, general questions, or small talk.

RULE 3 – MULTI-STEP PLANS:
When the user asks for something that requires multiple steps (e.g. "list problems AND proposals",
or "show me details of a specific scenario" which first requires listing scenarios to find the right id),
use a tool_plan with the full ordered sequence of tools needed to fulfil the request.

RULE 3b – CROSS-ENTITY RELATIONAL QUESTIONS:
When the user asks about relationships between entity types (e.g. "which proposals are associated
with this problem?", "what scenarios use these proposals?", "show me proposals for the problems
we just discussed"), the plan MUST:
  1. Fetch ALL entity lists that could contain the relationship field
     (e.g. for "proposals for a problem": list_available_problems AND list_available_proposals,
      because proposals store the problem_ids foreign key).
  2. Call get_context_ids with source_tools set to ALL fetched list keys so the LLM
     can follow the relationship fields across entity types.
  3. Then call get_context_details and interact_with_context as needed.
Do NOT call get_context_ids with only the list of the entity the user mentioned — always
include the lists of ALL entity types involved in the relationship.

RULE 4 – CONTEXT MUST BE FETCHED BEFORE QUERYING:
If interact_with_context is in the plan AND get_context_details has NOT already produced
results (check prior tool results), always prepend get_context_details to the plan.

RULE 5 – STAY ON TOPIC:
This platform is about tourism management, overtourism, mobility, and related decision-support.
If the user's request is unrelated to these topics, return:
  {{"action": "out_of_scope", "message": "..."}}

Previously collected tool results (available for argument resolution):
{prior_results_block}

Conversation so far:
{history_block}

New user message:
"{message}"

Available tools:
{tools_json}

Return ONLY valid JSON, with no explanation, no markdown fences, no extra text.
"""

    try:
        raw = llm_interaction(state, prompt).strip()
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

    if "tool_plan" in response_json:
        raw_plan = response_json["tool_plan"]
    elif response_json.get("tool_name"):
        raw_plan = [{"tool_name": response_json["tool_name"], "arguments": response_json.get("arguments", {})}]
    else:
        raw_plan = []

    tool_plan = [
        {"tool_name": step["tool_name"], "arguments": step.get("arguments", {})}
        for step in raw_plan
        if step.get("tool_name") and step["tool_name"] in available_tool_names
    ]

    for step in raw_plan:
        if step.get("tool_name") and step["tool_name"] not in available_tool_names:
            logger.warning(f"LLM planned unavailable tool '{step['tool_name']}', skipping")

    state.cognitive.tool_plan = tool_plan
    state.cognitive.tool_plan_index = 0

    if tool_plan:
        state.cognitive.selected_tool = tool_plan[0]["tool_name"]
        state.cognitive.tool_arguments = tool_plan[0]["arguments"]
    else:
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}

    state.add_trace(
        "tool_selection",
        "tool_selector",
        {"tool_plan": tool_plan, "available_tools": list(available_tool_names)},
    )

    logger.info(f"Tool plan: {tool_plan}")

    if tool_plan:
        return Command(update=state, goto="tool_executor")
    return Command(update=state, goto="generate_output_message")