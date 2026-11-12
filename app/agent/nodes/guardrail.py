"""
Topic guardrail helpers, shared by top_level_router_node and react_reasoner_node.

Two deterministic exits that never let an LLM "just answer":

  decline_off_topic(...)            the message is not about tourism management:
                                    nothing is answered, not even partially.
  escalate_to_general_knowledge()   the message IS on-topic but no grounded tool
                                    covers it: hand it to the exploitative tier
                                    (general_question_response) — which goes
                                    through the one-time consent gate — instead
                                    of letting the EXECUTOR relay a free-text
                                    answer the reasoner wrote from memory.

The EXECUTOR persona is only allowed to restate tool observations. Anything
that is not an observation has to leave through one of these two doors.
"""

import logging

from langgraph.types import Command

from app.agent.state import AgentState, AgentTier
from app.utils.territory import effective_user_request

logger = logging.getLogger(__name__)

GENERAL_TOOL = "general_question_response"

# English seed only: generate_answer relays it in state.user_lang through the
# dedicated decline prompt, which also forbids answering the original request.
DECLINE_SEED = (
    "The request is outside the scope of this assistant, which only supports "
    "tourism management (problems, proposals, scenarios, territorial indexes, "
    "analysis methodology)."
)

NO_GENERAL_ACCESS_SEED = (
    "The platform has no verified data to answer this, and an answer from general "
    "knowledge is not available to this user or mode. Invite the user to ask "
    "about platform data (problems, proposals, scenarios, territorial indexes) "
    "or about the analysis methodology."
)


def decline_off_topic(state: AgentState, node: str, reason: str = "") -> Command:
    """Finish the turn with a plain, content-free decline."""
    logger.info(f"Guardrail: declining off-topic request ({node}) {reason}")
    state.cognitive.guardrail_decline = True
    state.cognitive.pending_route_clarification = None
    state.waiting_for = None
    state.cognitive.selected_tool = None
    state.cognitive.tool_arguments = {}
    # Whatever may have been drafted so far is discarded on purpose: a decline
    # must never carry (part of) the answer.
    state.cognitive.messages_to_include = [DECLINE_SEED]
    state.add_trace(
        "guardrail_decline", node=node, data={"reason": reason or "off_topic"}
    )
    return Command(update=state, goto="generate_output_message")


def escalate_to_general_knowledge(
    state: AgentState, node: str, thought: str = ""
) -> Command:
    """Route an on-topic, ungrounded question to the exploitative tier."""
    already_tried = any(
        step.tool_name == GENERAL_TOOL for step in state.cognitive.scratchpad
    )
    can_use = (
        GENERAL_TOOL in (state.cognitive.known_tools or [])
        and state.allows_agent_tier(AgentTier.EXPLOITATIVE.value)
        and not already_tried
    )
    if not can_use:
        logger.info(f"Guardrail: general knowledge not available ({node})")
        state.cognitive.messages_to_include = [NO_GENERAL_ACCESS_SEED]
        state.add_trace("guardrail_no_general_access", node=node)
        return Command(update=state, goto="generate_output_message")

    enabled = list(state.cognitive.enabled_tools or [])
    if GENERAL_TOOL not in enabled:
        enabled.append(GENERAL_TOOL)
        state.cognitive.enabled_tools = enabled

    state.cognitive.selected_tool = GENERAL_TOOL
    state.cognitive.tool_arguments = {"query": effective_user_request(state)}
    state.cognitive.pending_thought = (
        thought or "No grounded tool covers this: escalate to the exploitative tier."
    )
    # A free-text finish message was discarded in favour of the tool call.
    state.cognitive.messages_to_include = []
    state.add_trace("guardrail_escalate_general", node=node)
    logger.info(f"Guardrail: escalating to {GENERAL_TOOL} ({node})")
    return Command(update=state, goto="tool_executor")
