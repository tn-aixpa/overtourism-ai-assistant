"""Territory selection helpers.

state.territory must always be one of state.allowed_territories before a
territory-scoped tool (ToolDefinition.requires_territory) runs. These helpers
centralise the matching/validation so the tool executor gate, the wait node
and the API layer all agree on what "admissible" means.
"""

import re
from typing import List, Optional

from app.agent.state import AgentState


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").strip().lower()).strip()


def is_valid_territory(state: AgentState, territory: Optional[str]) -> bool:
    return bool(territory) and territory in state.allowed_territories


def match_territories(text: str, allowed: List[str]) -> List[str]:
    """Allowed territories mentioned in `text`: a bare 1-based option number
    (matching the order shown in the question), or the territory name as a
    whole word / phrase (case- and punctuation-insensitive). Returns every
    distinct match, so callers can treat 0 matches as "not understood" and
    2+ as "ambiguous" instead of guessing."""
    normalized = _norm(text)
    if not normalized:
        return []

    leading_number = re.match(r"^(\d+)\b", normalized)
    if leading_number:
        idx = int(leading_number.group(1))
        if 1 <= idx <= len(allowed):
            return [allowed[idx - 1]]

    return [
        t
        for t in allowed
        if re.search(rf"\b{re.escape(_norm(t))}\b", normalized)
    ]


def resolve_territory_if_trivial(state: AgentState) -> bool:
    """Make state.territory valid without asking the user, when possible:
    already valid -> keep it; exactly one allowed territory -> take it for
    granted; exactly one allowed territory named in the user's last message
    -> use it. Returns whether state.territory is now valid. A stale value
    that is not in allowed_territories is treated as unset."""
    if is_valid_territory(state, state.territory):
        return True

    state.territory = ""
    allowed = state.allowed_territories
    if len(allowed) == 1:
        state.territory = allowed[0]
        return True

    last = state.get_last_user_message()
    if last is not None:
        # By-name match only: a bare number in a fresh message ("3
        # problems") must never be read as a menu choice.
        text = _norm(last.content)
        mentioned = [
            t for t in allowed if re.search(rf"\b{re.escape(_norm(t))}\b", text)
        ]
        if len(mentioned) == 1:
            state.territory = mentioned[0]
            return True
    return False


def territory_question(allowed: List[str]) -> str:
    options = "\n".join(f"{i}. {t}" for i, t in enumerate(allowed, start=1))
    return (
        "Which territory do you want to work on? Available territories:\n"
        f"{options}\n\nYou can reply with the name or the number."
    )


def mentioned_territory(state: AgentState) -> Optional[str]:
    """The single allowed territory named (as a whole word) in the user's last
    message, or None when none or several are named (ambiguous: never guess).
    By-name only, like resolve_territory_if_trivial."""
    last = state.get_last_user_message()
    if last is None:
        return None
    text = _norm(last.content)
    mentioned = [
        t for t in state.allowed_territories
        if re.search(rf"\b{re.escape(_norm(t))}\b", text)
    ]
    return mentioned[0] if len(mentioned) == 1 else None


def reset_territory_scoped_state(state: AgentState) -> None:
    """Forget everything that was fetched for the previous territory.

    Tool results, cached/retrieved entities, the current context, plot data,
    a pending temporary scenario and a retryable failed action all describe
    ONE territory's data. Leaving them in place after a switch makes the
    reasoner answer from the old territory's lists ("already retrieved")
    instead of querying the new one. Conversation history, route and tier
    consent are not territory data and are kept."""
    cog = state.cognitive
    cog.tool_results = {}
    cog.context_cache = {}
    cog.retrieved_context = {}
    cog.plot_data_cache = {}
    cog.current_context = {"problems": [], "proposals": [], "scenarios": []}
    cog.pending_temp_scenario = None
    cog.last_failed_action = None
    cog.tool_result = None


def switch_territory_if_requested(state: AgentState) -> Optional[str]:
    """At the start of a fresh user turn: if the user names a different
    allowed territory than the session's current one, switch to it and drop
    the old territory's data. Returns the previous territory when a switch
    happened, else None.

    Not applied in integrated mode (the host application fixes the territory
    there). A territory not in allowed_territories is never accepted."""
    if state.integrated_mode:
        return None
    target = mentioned_territory(state)
    if not target or target == state.territory:
        return None
    previous = state.territory
    state.territory = target
    reset_territory_scoped_state(state)
    return previous
