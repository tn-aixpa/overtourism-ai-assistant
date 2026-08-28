"""
Multi-level topic router — runs once per fresh turn, before react_reasoner,
to narrow the tool registry down to the domain the user's message actually
belongs to:

  1) system_info  — get_system_capabilities / lookup_glossary / links
  2) location      — problems, proposals, scenarios, analysis for a specific
                      location (tenant-scoped: Molveno, Altipiano di Fazzon)
  3) indexes       — territorial indexes for the whole region
  4) general       — general_question_response, for on-topic questions
                      nothing else can answer

Domains 2 and 3 have a second level that narrows further to a specific
tool sub-group (see route_groups.py).

Routing state (top_level_route / second_level_route) persists on
CognitiveState across turns, the same way tier_consent does — so an
ongoing conversation about, say, proposals does not get re-routed on every
message. Each turn still makes one lightweight classification call, but
that call's job is mostly "has the topic changed", not "start from
scratch" (see prompts/routing.classify_route).

When the classifier can't confidently place the message (or the user is
mid-conversation but the message doesn't fit the current route either),
this node pauses the turn and asks the user to pick from an explicit menu
of options, exactly like the tier-consent / creation-confirmation waits in
waiting.py — never guesses silently.
"""

import logging
import re

from langgraph.types import Command

from app.agent.state import AgentState
from app.agent.nodes import route_groups as rg
from app.prompts.routing import classify_route

logger = logging.getLogger(__name__)


def _numbered_options(options: dict[str, str]) -> list[tuple[int, str, str]]:
    """[(1-based position, option_key, label), ...] — a stable order used
    both for rendering the menu and for matching a numeric reply back to
    a key (dict order is insertion order, so this is consistent across the
    ask/answer round-trip as long as the same dict is used both times,
    which it always is here — route_groups.py's dicts are module-level
    constants)."""
    return [(i, key, label) for i, (key, label) in enumerate(options.items(), start=1)]


def _top_level_clarification_message() -> str:
    lines = [
        f"{i}. {label}" for i, _key, label in _numbered_options(rg.TOP_LEVEL_LABELS)
    ]
    return (
        "I want to make sure I look in the right place — is your question "
        "about:\n" + "\n".join(lines) + "\n\nCould you tell me which one (you can "
        "just reply with the number)?"
    )


def _second_level_clarification_message(top_level: str) -> str:
    lines = [
        f"{i}. {label}"
        for i, _key, label in _numbered_options(rg.sublevel_options(top_level))
    ]
    return (
        "Got it — within that area, are you asking about:\n"
        + "\n".join(lines)
        + "\n\nWhich one (you can just reply with the number)?"
    )


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.strip().lower()).strip()


def _match_numeric(user_input: str, options: dict[str, str]) -> str | None:
    """Resolve a bare leading number ("1", "2 please", ...) against the
    menu that was actually shown (dict order = display order, see
    _numbered_options). Language-independent and unambiguous, so this is
    checked first and never needs an LLM call. Returns None for anything
    that isn't (or doesn't start with) a valid option number — callers
    fall through to classify_route for free text."""
    normalized = _normalize(user_input)
    if not normalized:
        return None
    leading_number = re.match(r"^(\d+)\b", normalized)
    if not leading_number:
        return None
    idx = int(leading_number.group(1))
    for i, key, _label in _numbered_options(options):
        if i == idx:
            return key
    return None


def _apply_route(state: AgentState, top_level: str, second_level: str | None) -> None:
    state.cognitive.top_level_route = top_level
    state.cognitive.second_level_route = second_level

    allowed = rg.resolve_allowed_tools(top_level, second_level)
    if allowed is not None:
        # Derive from known_tools, NOT from the current enabled_tools.
        # enabled_tools is only guaranteed fresh on a turn that ran
        # initialize_tools's own reset (see reasoner.py) — but the
        # WAIT_USER_INPUT resume path (a route-clarification reply
        # arriving as its own follow-up request) skips initialize_tools
        # entirely and lands straight in this function, so relying on
        # whatever enabled_tools happened to already contain there is
        # fragile: if it were ever missing/stale across that request
        # boundary, intersecting against it would silently yield an empty
        # tool set for the rest of the turn — every tool call in the
        # resolved domain would look "unavailable" even though routing
        # itself resolved correctly. known_tools changes far less often
        # (once per session, unless the registry/integrated_mode itself
        # changes) and is exactly "every tool this session could ever
        # select" — the right base to filter down from regardless of
        # which path got us here.
        base = state.cognitive.known_tools or list(allowed)
        state.cognitive.enabled_tools = [name for name in base if name in allowed]


def _pause_for_clarification(
    state: AgentState, level: str, message: str, is_retry: bool = False
) -> Command:
    state.cognitive.pending_route_clarification = level
    state.cognitive.messages_to_include = [
        ("I didn't quite catch which one you meant — " + message)
        if is_retry
        else message
    ]
    state.waiting_for = AgentState.WaitingFor.ROUTE_CLARIFICATION
    state.user_input = None
    state.add_trace(
        "human_wait",
        node="TOP_LEVEL_ROUTER",
        data={"pending_route_clarification": level, "is_retry": is_retry},
    )
    return Command(update=state, goto="generate_output_message")


def resolve_clarification_reply(state: AgentState, level: str) -> Command:
    """
    Resolve a reply to a pending route-clarification menu (level "top" or
    "second", from state.cognitive.pending_route_clarification) into a
    route, or re-ask if it's still unclear. Called from WAIT_USER_INPUT
    once state.user_input holds the user's reply.

    A bare leading number ("1", "2 per favore", ...) is resolved directly
    against the menu that was actually shown (_match_numeric) — cheap,
    unambiguous, and language-independent, so no LLM call is needed for
    the common case of someone just answering with the option number.

    Anything else goes through classify_route — the SAME LLM classifier
    used for fresh-turn routing — rather than a hand-rolled keyword
    matcher. This deliberately replaced an earlier hardcoded English alias
    list (e.g. "system"/"capabilities" for system_info): this platform's
    users write in Italian, so a reply like "vorrei informazioni generali
    sul sistema" never matched anything and just re-showed the same menu
    forever. Free-text intent recognition across languages and phrasings
    is exactly what an LLM call is for; conversation history already
    includes the numbered menu we showed, so classify_route has everything
    it needs to map the reply back to an option. If the reply actually
    signals a different top-level domain than the one being asked about
    (e.g. the user changes their mind mid-second-level-menu), that's
    honored as a real route switch rather than forced into the stale menu.
    """
    user_input = state.user_input or ""
    state.user_input = None
    logger.info(f"Resolving route clarification ('{level}') reply: '{user_input}'")

    if level == "top":
        options = rg.TOP_LEVEL_LABELS
        numeric_choice = _match_numeric(user_input, options)
        if numeric_choice:
            state.cognitive.pending_route_clarification = None
            state.waiting_for = None
            return continue_from_resolved_top_level(
                state, numeric_choice, second_level_hint=None
            )

        classification = classify_route(state, None, None)
        top_level = classification["top_level"]
        if top_level in rg.TOP_LEVEL_LABELS:
            state.cognitive.pending_route_clarification = None
            state.waiting_for = None
            return continue_from_resolved_top_level(
                state, top_level, second_level_hint=classification["second_level"]
            )

        return _pause_for_clarification(
            state, "top", _top_level_clarification_message(), is_retry=True
        )

    # level == "second"
    current_top = state.cognitive.top_level_route
    options = rg.sublevel_options(current_top or "")
    numeric_choice = _match_numeric(user_input, options)
    if numeric_choice:
        state.cognitive.pending_route_clarification = None
        state.waiting_for = None
        return continue_from_resolved_top_level(
            state, current_top, second_level_hint=numeric_choice
        )

    classification = classify_route(state, current_top, None)
    classified_top = classification["top_level"]
    if (
        classification["topic_changed"]
        and classified_top in rg.TOP_LEVEL_LABELS
        and classified_top != current_top
    ):
        # The reply signals a genuinely different domain, not an answer to
        # the sub-area menu — re-route instead of forcing a fit.
        state.cognitive.pending_route_clarification = None
        state.waiting_for = None
        return continue_from_resolved_top_level(state, classified_top, second_level_hint=None)

    second_level = classification["second_level"]
    if current_top and second_level in rg.sublevel_options(current_top):
        state.cognitive.pending_route_clarification = None
        state.waiting_for = None
        return continue_from_resolved_top_level(
            state, current_top, second_level_hint=second_level
        )

    return _pause_for_clarification(
        state,
        "second",
        _second_level_clarification_message(current_top or ""),
        is_retry=True,
    )


def continue_from_resolved_top_level(
    state: AgentState, resolved_top: str, second_level_hint: str | None = None
) -> Command:
    """Given a top_level that is ALREADY decided (no classification call
    needed — used both by top_level_router_node once it has one, and
    directly by the WAIT_USER_INPUT resume path after the user picks an
    option from a menu, so a manual menu pick never triggers a second,
    redundant/fragile classification call over a one-word reply like "2"
    or "location"), resolve second_level if this domain needs one and
    hand off to react_reasoner — or pause again for a second-level menu.

    `second_level_hint`: a second_level value to accept if still valid for
    `resolved_top` (e.g. carried over from a persisted route, or a value
    the classifier already returned alongside top_level in the same call).
    """
    if not rg.has_sublevels(resolved_top):
        _apply_route(state, resolved_top, None)
        logger.info(f"Routed turn to top_level='{resolved_top}' (no sub-levels)")
        return Command(update=state, goto="react_reasoner")

    valid_subs = rg.sublevel_options(resolved_top)
    if second_level_hint in valid_subs:
        _apply_route(state, resolved_top, second_level_hint)
        logger.info(
            f"Routed turn to top_level='{resolved_top}', second_level='{second_level_hint}'"
        )
        return Command(update=state, goto="react_reasoner")

    logger.info(
        f"Second-level route unclear within '{resolved_top}', asking user to choose"
    )
    # Persist the top_level we already resolved, and narrow enabled_tools
    # to the domain-wide fallback (union of all its sub-groups), so the
    # wait-resume path (and a repeat ambiguous reply) doesn't have to
    # re-derive top_level from scratch, and tool scoping stays at least
    # domain-narrowed even while the second-level menu is pending.
    _apply_route(state, resolved_top, None)
    return _pause_for_clarification(
        state, "second", _second_level_clarification_message(resolved_top)
    )


def top_level_router_node(state: AgentState) -> Command:
    """Resolve (or re-resolve) this turn's domain via one classification
    call, then hand off to react_reasoner with the tool list scoped to
    that domain (see continue_from_resolved_top_level)."""

    current_top = state.cognitive.top_level_route
    current_second = state.cognitive.second_level_route

    classification = classify_route(state, current_top, current_second)
    top_level = classification["top_level"]
    topic_changed = classification["topic_changed"]
    second_level = classification["second_level"]

    # No persisted route yet, or the classifier says this message doesn't
    # belong to the current one anymore: (re)decide top_level from the
    # classification. Otherwise keep the persisted route untouched — this
    # is what avoids re-asking "which of the 4 areas?" every single turn.
    if current_top is None or topic_changed:
        if top_level not in rg.TOP_LEVEL_LABELS:
            logger.info("Top-level route unclear for message, asking user to choose")
            return _pause_for_clarification(
                state, "top", _top_level_clarification_message()
            )
        resolved_top = top_level
        # A genuine topic change always drops whatever second_level was
        # active for the old domain — it's meaningless in the new one.
        second_level_hint = second_level
    else:
        resolved_top = current_top
        second_level_hint = current_second

    return continue_from_resolved_top_level(state, resolved_top, second_level_hint)
