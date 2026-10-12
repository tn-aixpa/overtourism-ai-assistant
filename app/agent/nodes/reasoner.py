"""
ReAct reasoning nodes for the agentic system.

`initialize_tools` is the graph entry point (once per incoming user
message): it sets up the tool registry/allowlist and either resumes a
pending confirmation or starts a fresh ReAct loop by clearing the
scratchpad.

`react_reasoner_node` is the reasoning half of the Thought -> Action ->
Observation loop: on every visit it makes ONE LLM call to decide the single
next step (call a tool, or finish), publishes that thought live via the SSE
event bus, and routes to tool_executor or generate_output_message
accordingly. tool_executor_node routes back here after each observation, so
this node may be visited multiple times per user turn.
"""

import json
import logging
import re

from langgraph.types import Command

from app.agent.state import AgentState, AgentTier
from app.agent.events import publish_thought
from app.tools.tool_registry import (
    get_tool_registry,
    _ensure_tool_registry,
)
from app.prompts.react_reasoning import react_step

logger = logging.getLogger(__name__)


def initialize_tools(state: AgentState) -> Command:
    """
    Initialize available tools and route to react_reasoner.

    Entry point for both standard and integrated modes.
    If a confirmation flow is in progress, resumes it directly without
    touching the scratchpad (the loop is still mid-turn).
    """
    logger.info("Initializing available tools")

    if state.waiting_for and state.user_input:
        logger.info(
            f"Resuming from waiting_for={state.waiting_for}, routing to WAIT_USER_INPUT"
        )
        return Command(update=state, goto="WAIT_USER_INPUT")

    registry = _ensure_tool_registry()

    allowlist = state.cognitive.known_tools or None
    # No tier filtering here: which tools are selectable this turn is
    # governed entirely by routing (top_level_router_node scopes
    # enabled_tools further down below), not by the tier a tool's response
    # would be generated under (see ToolDefinition.agent_tier).
    #
    # role/mode filtering (ToolDefinition.allowed_roles / allowed_modes,
    # see app.tools.tool_schema) IS applied here, via state.user_role /
    # state.session_mode — e.g. this is what keeps widget tools
    # (show_analysis_widget, show_territorial_index_map, both declared
    # allowed_modes={"standalone"}) out of integrated-mode sessions, now
    # declaratively on the tools themselves instead of a hardcoded
    # WIDGET_TOOL_NAMES exclusion list here. Computed fresh from THIS
    # session's state on every call and only ever narrows a per-request
    # copy of known_tools/enabled_tools in AgentState — it must never
    # mutate the ToolRegistry itself, which is a process-wide singleton
    # (see get_tool_registry) shared by every session's worker thread.
    known_tools = registry.get_context_tools(
        allowlist=allowlist,
        role=state.user_role,
        mode=state.session_mode,
    )

    state.cognitive.known_tools = list(known_tools.keys())

    if state.integrated_mode:
        if not state.cognitive.enabled_tools:
            state.cognitive.enabled_tools = state.cognitive.known_tools
        # Re-narrow to known_tools rather than re-checking role/mode here:
        # known_tools has already had the same role/mode filter applied
        # above, so intersecting against it (instead of duplicating the
        # is_allowed_for check) keeps this in sync with it by construction.
        state.cognitive.enabled_tools = [
            name for name in state.cognitive.enabled_tools if name in known_tools
        ]
    else:
        state.cognitive.enabled_tools = list(state.cognitive.known_tools)

    logger.info(f"Available tools: {state.cognitive.enabled_tools}")

    # Fresh user turn: reset the working memory for the ReAct loop. Long-term
    # memory (tool_results) is intentionally left untouched.
    state.assistant_action_data = None
    state.cognitive.scratchpad = []
    state.cognitive.selected_tool = None
    state.cognitive.tool_arguments = {}
    state.cognitive.pending_thought = ""
    state.cognitive.tool_confirmation_needed = False
    state.cognitive.tool_confirmed = False
    # active_agent reflects the highest-tier tool actually used THIS turn
    # (see tool_executor_node._bump_active_agent) — reset to the EXECUTOR
    # baseline at the start of every fresh turn so a previous turn's tier
    # never leaks into this one's response style. This is deliberately NOT
    # persisted across turns, unlike top_level_route/second_level_route
    # below and tier_consent (state.cognitive.tier_consent) — those track
    # "where we are" / "what's been permitted", active_agent tracks "what
    # kind of response this turn earned".
    state.active_agent = AgentTier.EXECUTOR

    # Route the turn to the right domain (and scope enabled_tools to it)
    # before the ReAct loop starts reasoning about which specific tool to
    # call. top_level_route/second_level_route persist on CognitiveState
    # across turns — see top_level_router_node for when it re-asks vs.
    # keeps the session's current route.
    return Command(update=state, goto="top_level_router")


def react_reasoner_node(state: AgentState) -> Command:
    """
    One Thought/Action decision. Called once per cycle of the ReAct loop.
    """
    logger.info(f"Entering react_reasoner (step {len(state.cognitive.scratchpad) + 1})")

    registry = get_tool_registry()
    # role/mode must be passed here too, not just in initialize_tools:
    # enabled_tools (the allowlist below) was already narrowed by routing
    # and is names-only, it carries no role/mode information of its own.
    # get_tools_for_llm -> get_context_tools re-applies is_allowed_for
    # against whatever role/mode it's given, and is_allowed_for fails
    # CLOSED for role=None/mode=None on any tool that declares a
    # restriction (see ToolDefinition.is_allowed_for) — which by now is
    # nearly every tool. Omitting these here doesn't just skip a filter,
    # it flips it to "reject everything", silently emptying
    # tools_for_llm_enabled even though enabled_tools/known_tools are
    # completely correct.
    tools_for_llm_enabled = registry.get_tools_for_llm(
        allowlist=state.cognitive.enabled_tools,
        role=state.user_role,
        mode=state.session_mode,
    )

    # Tell the reasoner why a tool is absent without conflating role and
    # mode restrictions. These are whole-session candidate tools (before
    # routing narrows enabled_tools), so out-of-scope tools are not reported.
    role_unavailable_tool_names = []
    mode_unavailable_tool_names = []
    for name, tool in registry.get_all_known_tools().items():
        role_allowed = (
            tool.allowed_roles is None or state.user_role in tool.allowed_roles
        )
        mode_allowed = (
            tool.allowed_modes is None or state.session_mode in tool.allowed_modes
        )
        if not role_allowed:
            role_unavailable_tool_names.append(name)
        if not mode_allowed:
            mode_unavailable_tool_names.append(name)
    role_unavailable_tool_names.sort()
    mode_unavailable_tool_names.sort()

    if not tools_for_llm_enabled:
        logger.warning("No tools available for this context")
        state.cognitive.messages_to_include = [
            "No tools are available in the current context."
        ]
        return Command(update=state, goto="generate_output_message")

    # Safety valve: never loop forever if the model keeps calling tools
    # without ever finishing.
    if len(state.cognitive.scratchpad) >= state.cognitive.max_react_steps:
        logger.warning("Max ReAct steps reached, forcing finish")
        state.add_trace(
            "react_step_limit",
            "react_reasoner",
            {"steps": len(state.cognitive.scratchpad)},
        )
        # messages_to_include is left empty on purpose: generate_output_message
        # will fall back to synthesizing from every observation collected
        # this turn (see general.py), which is the best we can offer here.
        return Command(update=state, goto="generate_output_message")

    try:
        raw = react_step(
            state,
            tools_for_llm_enabled,
            mode_unavailable_tool_names,
            role_unavailable_tool_names,
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        response_json = json.loads(raw)
    except Exception as e:
        logger.exception("Error parsing ReAct reasoning response")
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")

    thought = response_json.get("thought", "")
    action = response_json.get("action")

    if thought:
        publish_thought(state.session_id, thought)

    state.add_trace(
        "react_thought",
        "react_reasoner",
        {
            "thought": thought,
            "action": action,
            "step": len(state.cognitive.scratchpad) + 1,
        },
    )

    if action == "tool":
        tool_name = response_json.get("tool_name")
        arguments = response_json.get("arguments", {}) or {}
        enabled_tool_names = {t["function"]["name"] for t in tools_for_llm_enabled}

        if not tool_name or tool_name not in enabled_tool_names:
            logger.warning(
                f"Reasoner selected unavailable tool '{tool_name}', finishing instead"
            )
            state.cognitive.messages_to_include = [
                "The current request cannot be handled in the current context. "
                "Please change context or use the standalone chat."
            ]
            return Command(update=state, goto="generate_output_message")

        # Start a new scratchpad entry for this action; tool_executor fills
        # in the observation and appends it once the tool has run.
        state.cognitive.selected_tool = tool_name
        state.cognitive.tool_arguments = arguments
        state.cognitive.pending_thought = thought

        logger.info(f"ReAct action decided: {tool_name}({arguments})")
        return Command(update=state, goto="tool_executor")

    # action == "finish" (or anything else we don't recognise -> finish safely)
    message = response_json.get("message") or "Could you clarify your request?"
    state.cognitive.messages_to_include = [message]
    logger.info(f"ReAct loop finishing: {message}")
    return Command(update=state, goto="generate_output_message")
