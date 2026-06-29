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

    allowlist = state.cognitive.known_tools or None
    known_tools = registry.get_context_tools(allowlist=allowlist)
    state.cognitive.known_tools = list(known_tools.keys())

    logger.info(f"Available tools: {state.cognitive.known_tools}")
    return Command(update=state, goto="tool_selector")


def tool_selector_node(state: AgentState) -> Command:
    logger.info("Entering tool selector node")

    registry = get_tool_registry()
    tools_for_llm = registry.get_tools_for_llm(allowlist=None)
    tools_for_llm_enabled = registry.get_tools_for_llm(allowlist=state.cognitive.enabled_tools)

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
    available_tools_json = json.dumps(tools_for_llm_enabled, indent=2)

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

Tool unavailable:
{{
  "action": "tool_unavailable",
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

RULE 4 – CONTEXT MUST BE FETCHED BEFORE QUERYING:
If interact_with_context is in the plan AND get_context_details has NOT already produced
results (check prior tool results), always prepend get_context_details to the plan.

RULE 5 – STAY ON TOPIC:
This platform is about tourism management, overtourism, mobility, and related decision-support.
If the user's request is unrelated to these topics, return:
  {{"action": "out_of_scope", "message": "..."}}

RULE 6 – CREATION REQUESTS (not yet implemented):
If the user wants to create, add, or register a new Problem, Proposal, or Scenario,
map the intent to the corresponding tool:
  - create_new_problem  → user wants to add/create a problem
  - create_new_proposal → user wants to add/create a proposal or strategy
  - create_new_scenario → user wants to add/create a scenario or simulation
These tools are stubs: they will acknowledge the request and explain the feature is
coming soon. Extract as much of name/description/parent-id from the user message as
possible and pass them as arguments, so the response feels personal.

RULE 7 – GLOSSARY / TERMINOLOGY QUESTIONS:
If the user asks what a term means, asks for a definition, or uses vocabulary that is
ambiguous and might map to a platform concept (e.g. "what is a scenario?",
"what do you mean by proposal?", "cosa è un problema?"), call:
  {{"tool_name": "lookup_glossary", "arguments": {{"query": "<the term(s) to look up>"}}}}
You MAY also call lookup_glossary as a silent first step in a plan when the user intent
is unclear and a terminology lookup would help you understand what entity type they mean.

RULE 8 – TOOL AVAILABILITY

The assistant knows about all tools listed under "Known tools", but may execute only the
tools listed under "Tools available in the current execution mode".

If the user's request would normally require a known tool that is not available in the
current execution mode:

- Do NOT choose another tool as a substitute.
- Do NOT answer from memory.
- Do NOT classify the request as out_of_scope.
- Return

{{
  "action": "tool_unavailable",
  "tool": "<tool_name>",
  "message": "..."
}}

Previously collected tool results (available for argument resolution):
{prior_results_block}

Conversation so far:
{history_block}

New user message:
"{message}"

Known tools:
{tools_json}

Tools available in the current execution mode:
{available_tools_json}

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
    
    if action == "tool_unavailable":
        state.cognitive.messages_to_include = [
            response_json.get("message", "The current request cannot be handle in the current context. Please change contex or use the standalone chat.")
        ]
        return Command(update=state, goto="generate_output_message")

    if action == "out_of_scope":
        state.cognitive.messages_to_include = [
            response_json.get("message", "That request is outside my scope.")
        ]
        return Command(update=state, goto="generate_output_message")

    enabled_tool_names = {
        t["function"]["name"]
        for t in tools_for_llm_enabled
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
        if step.get("tool_name") and step["tool_name"] in enabled_tool_names
    ]

    for step in raw_plan:
        if step.get("tool_name") and step["tool_name"] not in enabled_tool_names:
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
        {"tool_plan": tool_plan, "known_tools": list(enabled_tool_names)},
    )

    logger.info(f"Tool plan: {tool_plan}")

    if tool_plan:
        return Command(update=state, goto="tool_executor")
    return Command(update=state, goto="generate_output_message")