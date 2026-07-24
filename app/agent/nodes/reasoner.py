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

from app.agent.state import AgentState
from app.agent.events import publish_thought
from app.tools.tool_registry import get_tool_registry, _ensure_tool_registry
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
    known_tools = registry.get_context_tools(allowlist=allowlist)
    state.cognitive.known_tools = list(known_tools.keys())

    # In non-integrated mode enabled_tools is not pre-set by the route, so
    # make all known tools available. In integrated mode the route already
    # wrote the restricted allowlist and we must not overwrite it.
    if not state.integrated_mode:
        state.cognitive.enabled_tools = state.cognitive.known_tools

    logger.info(f"Available tools: {state.cognitive.enabled_tools}")

    # Fresh user turn: reset the working memory for the ReAct loop. Long-term
    # memory (tool_results) is intentionally left untouched.
    state.cognitive.scratchpad = []
    state.cognitive.selected_tool = None
    state.cognitive.tool_arguments = {}
    state.cognitive.pending_thought = ""
    state.cognitive.tool_confirmation_needed = False
    state.cognitive.tool_confirmed = False

    return Command(update=state, goto="react_reasoner")


def react_reasoner_node(state: AgentState) -> Command:
    """
    One Thought/Action decision. Called once per cycle of the ReAct loop.
    """
    logger.info(f"Entering react_reasoner (step {len(state.cognitive.scratchpad) + 1})")

    registry = get_tool_registry()
    tools_for_llm = registry.get_tools_for_llm(allowlist=None)
    tools_for_llm_enabled = registry.get_tools_for_llm(
        allowlist=state.cognitive.enabled_tools
    )

    if not tools_for_llm:
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
        raw = react_step(state, tools_for_llm, tools_for_llm_enabled)
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
