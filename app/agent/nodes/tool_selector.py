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
    from app.utils.llm import llm_interaction, format_messages

    message = (state.get_last_user_message() or "").content
    history = state.get_reasoning_context()
    history_block = format_messages(history) if history else "None"
    tools_json = json.dumps(tools_for_llm, indent=2)
    available_tools_json = json.dumps(tools_for_llm_enabled, indent=2)

    prior_results_block = "None"
    if state.cognitive.tool_results:
        prior_results_block = json.dumps(
            state.cognitive.tool_results, indent=2, default=str
        )

    prompt = f"""
You are an assistant for a digital twin platform named AIxPA related to tourism management.

Follow the steps below IN ORDER. Stop at the first step that applies and return its JSON. Do not skip ahead.

============================================================
STEP 1 — TOOL AVAILABILITY CHECK
============================================================
Look at "Tools available in the current execution mode" below.
If answering this message would require a tool from "Known tools" that is NOT in that list,
return exactly this and STOP:
{{"action": "tool_unavailable", "tool": "<tool_name>", "message": "..."}}

============================================================
STEP 2 — IS THIS A GREETING OR GENERAL QUESTION?
============================================================
Check ONLY this: is the message a greeting ("Ciao", "Hello", "Hi"), a thank-you, small talk,
or a question about what the system can do in general?
If YES, return exactly this and STOP:
{{"tool_name": "get_system_capabilities", "arguments": {{}}}}
If NO, go to Step 3.
(Do this check BEFORE the topic check in Step 3. A greeting is never "out of scope".)

============================================================
STEP 3 — IS THIS ON TOPIC?
============================================================
The platform covers: tourism management, overtourism, mobility, problems, proposals,
scenarios, and related decision-support.
If the message is clearly about something else, return exactly this and STOP:
{{"action": "out_of_scope", "message": "..."}}
If it is on topic (or you're unsure), go to Step 4.

============================================================
STEP 4 — IS THE USER ASKING FOR A DEFINITION?
============================================================
If the user asks what a term means, or uses ambiguous vocabulary that might be a platform
concept (e.g. "what is a scenario?", "cosa è un problema?"), return:
{{"tool_name": "lookup_glossary", "arguments": {{"query": "<term(s)>"}}}}
You may also put lookup_glossary as the FIRST step of a tool_plan (see Step 6) if you are
unsure which entity type (problem/proposal/scenario) the user means.

============================================================
STEP 5 — IS THE USER ASKING FOR DETAILS ABOUT SOMETHING SPECIFIC?
============================================================
Only use get_context_details or interact_with_context when the user explicitly refers to
a specific existing problem, proposal, or scenario. Never use them for greetings or general
questions (those were already handled in Step 2).

If the entity is referred to by NAME/DESCRIPTION rather than an explicit ID, and it has not
already been resolved into current_context by a get_context_ids call earlier in this plan or
conversation, you MUST build a tool_plan that resolves it first:
  list_available_problems / list_available_proposals / list_available_scenarios (whichever
  is appropriate, skip if already run and present in "Previously collected tool results"),
  then get_context_ids with the user's intent and that source tool,
  and ONLY THEN get_context_details.

Rule: if interact_with_context is used and get_context_details has not already produced
results (check "Previously collected tool results"), put get_context_details BEFORE it in
the tool_plan (after the resolution steps above, if needed).

============================================================
STEP 6 — IS THE USER ASKING TO CREATE, EDIT, OR DELETE SOMETHING?
============================================================
Map the request to ONE of these tools:
  create_new_problem, create_new_proposal, create_new_scenario,
  edit_problem, edit_proposal, edit_scenario,
  delete_problem, delete_proposal, delete_scenario

Extract only name/description details the user actually typed. Never invent details,
never suggest your own mitigation ideas or strategies as arguments.

--- ID CHECKLIST — do this every time before calling one of the 9 tools above ---
Every one of these 9 tools needs an id. NEVER type/guess/pattern-match an id string yourself.

Important: the user almost never knows or types the literal id. They refer to problems,
proposals, and scenarios by name or description instead — e.g. "the second problem",
"the parking problem", "the strategy about bike lanes". Expect Q1 below to usually be NO.

Go through these questions in order:

  Q1. Does the id needed by the tool already appear as an EXPLICIT id string (not a name
      or description) in the user message or earlier in the conversation?
      → YES: use it directly in "arguments".
      → NO (most common case): go to Q2.

  Q2. Which id does the tool need?
      - create_new_proposal, edit_proposal, delete_proposal  → needs a PROBLEM id (the parent)
      - create_new_scenario, edit_scenario, delete_scenario  → needs a PROPOSAL id (the parent)
      - create_new_problem                                    → no parent id needed
      - edit_problem, delete_problem                          → needs a PROBLEM id (the target itself)
      - edit_proposal, delete_proposal                        → also needs the PROPOSAL id (the target itself)
      - edit_scenario, delete_scenario                        → also needs the SCENARIO id (the target itself)

      (Note: edit_proposal/delete_proposal only need the proposal's own id, not a problem id,
       unless you are also changing which problem it belongs to. Same logic for scenario tools.)

  Q3. Build a tool_plan that resolves the id BEFORE calling the creation/edit/delete tool:
      - need a PROBLEM id  → list_available_problems, then get_context_ids
      - need a PROPOSAL id → list_available_proposals, then get_context_ids
      - need a SCENARIO id → list_available_scenarios, then get_context_ids
      Then add the creation/edit/delete tool as the LAST step.
      In that last step's "arguments", OMIT the id field entirely. Do not fill it with a
      guess. The executor resolves it automatically from the get_context_ids result.

============================================================
STEP 7 — NOTHING ABOVE APPLIED
============================================================
If none of the steps above matched, return a clarification:
{{"action": "clarify", "message": "..."}}

============================================================
OUTPUT FORMAT
============================================================
Return ONE of these JSON shapes only. No markdown, no explanation, no extra text.

Multiple tools in sequence:
{{"tool_plan": [{{"tool_name": "<name>", "arguments": {{}}}}, {{"tool_name": "<name>", "arguments": {{}}}}]}}

Single tool:
{{"tool_name": "<name>", "arguments": {{}}}}

Clarification:
{{"action": "clarify", "message": "..."}}

Out of scope:
{{"action": "out_of_scope", "message": "..."}}

Tool unavailable:
{{"action": "tool_unavailable", "tool": "<name>", "message": "..."}}

No action needed:
{{"tool_name": null, "arguments": {{}}}}

============================================================
CONTEXT
============================================================
Previously collected tool results (use these for argument resolution):
{prior_results_block}

Conversation so far:
{history_block}

New user message:
"{message}"

Known tools:
{tools_json}

Tools available in the current execution mode:
{available_tools_json}

Return ONLY valid JSON.
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
