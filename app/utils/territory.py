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
