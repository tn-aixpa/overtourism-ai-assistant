from langgraph.types import Command
import logging
import re

from app.agent.state import AgentState, ReActStep
from app.agent.nodes.router import resolve_clarification_reply

logger = logging.getLogger(__name__)


def _resolve_proposal_name(state: AgentState, proposal_id: str) -> str:
    """Look up a proposal's display name for the confirmation recap, so the
    user sees the name they typed rather than the raw proposal_id. Falls
    back to the raw id if the proposal hasn't been fetched/listed yet this
    session (e.g. the id was typed explicitly rather than resolved from a
    prior list_available_proposals call)."""
    if not proposal_id:
        return proposal_id

    cached = state.cognitive.context_cache.get(f"proposals {proposal_id}", {})
    if cached.get("name"):
        return cached["name"]

    for key, value in state.cognitive.tool_results.items():
        if key == "list_available_proposals" or key.startswith(
            "list_available_proposals__"
        ):
            if isinstance(value, list):
                for item in value:
                    if (
                        isinstance(item, dict)
                        and item.get("proposal_id") == proposal_id
                    ):
                        return item.get("name", proposal_id)

    return proposal_id


def _wait_instructions(state: AgentState) -> str:
    """Generate confirmation message for the pending tool, recapping every
    piece of data that is about to be submitted."""
    pending_tool = state.cognitive.selected_tool
    args = state.cognitive.tool_arguments or {}

    def _format_fields(fields: dict) -> str:
        lines = []
        for key, value in fields.items():
            if value is None or value == "":
                continue
            label = key.replace("_", " ").capitalize()
            lines.append(f"- {label}: {value}")
        return "\n".join(lines) if lines else "- (no additional data provided)"

    if pending_tool in [
        "create_new_problem",
        "create_new_proposal",
        "create_new_scenario",
    ]:
        fields = dict(args)
        if pending_tool == "create_new_scenario":
            pending_values = (state.cognitive.pending_temp_scenario or {}).get("values")
            if pending_values:
                fields["values"] = pending_values
            proposal_id = fields.pop("proposal_id", None)
            if proposal_id:
                fields["proposal"] = _resolve_proposal_name(state, proposal_id)
        return (
            "Before I submit this, please confirm the details below are correct:\n"
            f"{_format_fields(fields)}\n\nShall I proceed?"
        )

    return "Please confirm to proceed."


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation so 'Yes, go ahead!' and 'yes' match
    the same way — the confirmation/cancellation sets below are otherwise
    exact-string-only, which misses almost any natural phrasing."""
    return re.sub(r"[^\w\s]", " ", text.strip().lower()).strip()


def _contains_any_phrase(normalized_text: str, phrases: set[str]) -> bool:
    """Whole-word/phrase containment check (not a bare substring check, so
    e.g. 'nostalgic' doesn't accidentally match 'no')."""
    return any(
        re.search(rf"\b{re.escape(phrase)}\b", normalized_text) for phrase in phrases
    )


def _is_confirmation(user_input: str) -> bool:
    """Check if the user input is a confirmatory reply.

    Matches the whole normalized input against the confirmatory set (as
    before) OR checks whether a confirmatory phrase appears anywhere in a
    longer natural reply (e.g. "yes, go ahead", "sure, sounds good").
    If a cancellation phrase is also present, cancellation wins — treating
    an ambiguous/negated reply ("no, not sure") as anything other than "not
    confirmed" would be the unsafe direction for a create/edit/delete gate.
    """
    normalized = _normalize(user_input)
    if not normalized:
        return False
    if _contains_any_phrase(normalized, _CANCELLATION_PHRASES):
        return False
    return normalized in _CONFIRMATORY_PHRASES or _contains_any_phrase(
        normalized, _CONFIRMATORY_PHRASES
    )


def _is_cancellation(user_input: str) -> bool:
    """Check if the user input is a cancellation (see _is_confirmation)."""
    normalized = _normalize(user_input)
    if not normalized:
        return False
    return normalized in _CANCELLATION_PHRASES or _contains_any_phrase(
        normalized, _CANCELLATION_PHRASES
    )


_CONFIRMATORY_PHRASES = {
    "ok",
    "okay",
    "yes",
    "yeah",
    "yep",
    "sure",
    "proceed",
    "go ahead",
    "confirm",
    "correct",
    "fine",
    "agreed",
    "sounds good",
    "sì",
    "si",
    "va bene",
    "procedi",
    "confermo",
    "esatto",
    "ja",
    "gut",
    "weiter",
    "oui",
    "d'accord",
    "да",
}

_CANCELLATION_PHRASES = {
    "no",
    "cancel",
    "stop",
    "abort",
    "nevermind",
    "never mind",
    "no grazie",
    "annulla",
    "nein",
    "non",
}

# Normalize the phrase sets themselves through the same function used on
# user input (e.g. "d'accord" -> "d accord"), so punctuation inside a phrase
# doesn't cause a mismatch against the punctuation-stripped input.
_CONFIRMATORY_PHRASES = {_normalize(p) for p in _CONFIRMATORY_PHRASES}
_CANCELLATION_PHRASES = {_normalize(p) for p in _CANCELLATION_PHRASES}


_CONFIRMATION_WAITING_FOR = {
    "create_new_problem": AgentState.WaitingFor.PROBLEM_CONFIRMATION,
    "create_new_proposal": AgentState.WaitingFor.PROPOSAL_CONFIRMATION,
    "create_new_scenario": AgentState.WaitingFor.SCENARIO_CONFIRMATION,
}


def _tier_consent_instructions() -> str:
    """Confirmation message for a gated-tier access request. Deliberately
    generic (not a data recap like _wait_instructions) since what's being
    confirmed is permission to use a capability, not specific field values.
    """
    return (
        f"To answer this question I need to use unverified sources "
        "and so the answer cannot be fully trusted. "
        "Do you still want me to reply? I won't ask again for a while."
    )


def wait_user_input_node(state: AgentState):
    """Wait node — dispatches between the three kinds of pause this graph
    can be in: a routing menu (pending_route_clarification set), a
    gated-tier access request (pending_tier_consent set), or a
    create/edit/delete data confirmation (the original, tool-keyed flow).
    See _handle_route_clarification_wait / _handle_tier_consent_wait /
    _handle_creation_confirmation_wait.
    """
    if state.cognitive.pending_route_clarification:
        return _handle_route_clarification_wait(state)
    if state.cognitive.pending_tier_consent:
        return _handle_tier_consent_wait(state)
    return _handle_creation_confirmation_wait(state)


def _handle_route_clarification_wait(state: AgentState):
    """
    Wait node for the top-level/second-level topic router (see
    app.agent.nodes.router.top_level_router_node).

    - If no user_input yet: the router already put the menu text in
      messages_to_include and set waiting_for before routing here — just
      emit it, same persist/resume mechanics as the other wait flows.
    - If the user replied: hand off to router.resolve_clarification_reply,
      which resolves a bare option number directly and falls back to the
      same LLM classifier used for fresh-turn routing for anything else
      (free text, any language) — see that function's docstring for why
      this isn't a hardcoded keyword matcher. It either resolves the route
      and returns a Command routed onward, or re-pauses with a fresh menu
      if still unclear.
    """
    level = state.cognitive.pending_route_clarification

    if not state.user_input:
        state.waiting_for = AgentState.WaitingFor.ROUTE_CLARIFICATION
        state.add_trace(
            "human_wait",
            node="WAIT_USER_INPUT",
            data={"pending_route_clarification": level},
        )
        return Command(update=state, goto="generate_output_message")

    return resolve_clarification_reply(state, level)


def _handle_tier_consent_wait(state: AgentState):
    """
    Wait node for gated-tier access consent.

    - If no user_input yet: ask permission and route to generate_output_message,
      same persist/resume mechanics as the creation-confirmation flow below.
    - If user confirms: grant consent (persisted on CognitiveState.tier_consent,
      not just for this turn) and resume at tier_consent_resume_goto — for
      today's only caller (tool_executor_node) that re-enters tool_executor,
      whose gate now passes since consent was just granted.
    - If user declines: do NOT end the turn like a creation-confirmation
      cancellation does. Record an Observation on the scratchpad so the
      calling agent sees the decline and can adapt (explain the limitation,
      fall back to a grounded answer) on its own, then hand back to the
      reasoner to keep going.
    - Otherwise: ask again without discarding the pending request.
    """
    tier = state.cognitive.pending_tier_consent

    if not state.user_input:
        state.cognitive.messages_to_include = [_tier_consent_instructions()]
        state.waiting_for = AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        state.add_trace(
            "human_wait",
            node="WAIT_USER_INPUT",
            data={"pending_tier_consent": tier},
        )
        return Command(update=state, goto="generate_output_message")

    user_input = state.user_input.strip()
    logger.info(f"User replied to tier-consent request ('{tier}'): '{user_input}'")

    if _is_confirmation(user_input):
        logger.info(f"User granted access to tier '{tier}'")
        state.cognitive.grant_tier_consent(tier)
        resume_goto = state.cognitive.tier_consent_resume_goto or "tool_executor"
        state.cognitive.pending_tier_consent = None
        state.cognitive.tier_consent_resume_goto = None
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto=resume_goto)

    if _is_cancellation(user_input):
        logger.info(f"User declined access to tier '{tier}' — continuing without it")
        state.cognitive.scratchpad.append(
            ReActStep(
                thought=state.cognitive.pending_thought,
                tool_name=state.cognitive.selected_tool,
                tool_arguments=state.cognitive.tool_arguments,
                observation={
                    "success": False,
                    "error": f"User declined access to the '{tier}' tier for this turn.",
                },
                status="tier_access_declined",
            )
        )
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.pending_thought = ""
        state.cognitive.pending_tier_consent = None
        state.cognitive.tier_consent_resume_goto = None
        state.waiting_for = None
        state.user_input = None
        # Hand back to the reasoner (today's only loop) rather than ending
        # the turn, so it can react to the decline instead of the turn
        # dead-ending on a bare "I won't do that". Once tiers are separate
        # nodes, this should resume whatever tier is actually still active
        # (e.g. the tier that attempted the delegation), not always
        # "react_reasoner".
        return Command(update=state, goto="react_reasoner")

    # Ambiguous reply: keep the pending request alive, ask for a clear
    # yes/no, same pattern as the creation-confirmation flow.
    state.cognitive.messages_to_include = [
        "I’m not sure whether that’s a yes or no — could you confirm clearly "
        "whether I should use it?"
    ]
    state.waiting_for = AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
    state.user_input = None
    return Command(update=state, goto="generate_output_message")


def _handle_creation_confirmation_wait(state: AgentState):
    """
    Wait node for tool confirmation.

    - If no user_input yet: set confirmation prompt in messages_to_include, publish it live
      via the event bus, and route to generate_output_message. The API layer detects
      waiting_for is set and persists state; the next request will re-enter with user_input
      populated.
    - If user confirms: route to tool_executor to run the pending create/edit/delete tool.
    - If user cancels: clear the pending action and route to generate_output_message.
    - Otherwise: route back to initialize_tools to re-interpret the new input as a fresh turn.
    """
    logger.info(
        f"Entered WAIT_USER_INPUT node. Pending tool: {state.cognitive.selected_tool}"
    )

    if not state.user_input:
        # First pass: populate messages_to_include with the confirmation prompt and
        # route to generate_output_message to emit it. The graph will then END;
        # waiting_for stays set on the persisted state so the next invocation
        # re-enters here with user_input populated.
        instructions = _wait_instructions(state)
        state.cognitive.messages_to_include = [instructions]
        state.waiting_for = _CONFIRMATION_WAITING_FOR.get(
            state.cognitive.selected_tool, AgentState.WaitingFor.CONTEXT_INPUT
        )

        state.add_trace(
            "human_wait",
            node="WAIT_USER_INPUT",
            data={"pending_tool": state.cognitive.selected_tool},
        )
        return Command(update=state, goto="generate_output_message")

    # Second pass: user has replied
    user_input = state.user_input.strip()
    logger.info(f"User replied while waiting: '{user_input}'")

    if _is_cancellation(user_input):
        logger.info("User cancelled — clearing pending action")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.pending_thought = ""
        state.cognitive.tool_confirmation_needed = False
        state.cognitive.tool_confirmed = False
        state.waiting_for = None
        state.user_input = None
        state.cognitive.messages_to_include = [
            "Okay, I won't submit this — let me know if you'd like to change anything or start over."
        ]
        return Command(update=state, goto="generate_output_message")

    if _is_confirmation(user_input):
        logger.info("User confirmed — proceeding to tool_executor")
        state.cognitive.tool_confirmation_needed = False
        state.cognitive.tool_confirmed = True
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto="tool_executor")

    # Ambiguous reply: keep the pending confirmation alive, ask for a clear
    # yes/no answer, and do not discard the tool or its arguments.
    logger.info(
        "Ambiguous reply — asking for clarification without clearing pending confirmation"
    )
    state.cognitive.messages_to_include = [
        "I’m not sure whether you want me to proceed or cancel. Please reply with a clear confirmation such as 'yes' to proceed or 'no' to cancel."
    ]
    state.waiting_for = _CONFIRMATION_WAITING_FOR.get(
        state.cognitive.selected_tool, AgentState.WaitingFor.CONTEXT_INPUT
    )
    state.user_input = None
    return Command(update=state, goto="generate_output_message")
