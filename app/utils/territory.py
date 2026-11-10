"""Territory selection helpers.

state.territory must always be one of state.allowed_territories before a
territory-scoped tool (ToolDefinition.requires_territory) runs. These helpers
centralise the matching/validation so the tool executor gate, the wait node
and the API layer all agree on what "admissible" means.
"""

import difflib
import re
from typing import List, Optional

from app.agent.state import AgentState


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").strip().lower()).strip()


def display_territory(territory: str) -> str:
    """Capitalize the first character for user-facing territory names."""
    return territory[:1].upper() + territory[1:]


def is_valid_territory(state: AgentState, territory: Optional[str]) -> bool:
    return bool(territory) and territory in state.allowed_territories


# A typo of a territory name ("Moleno" for Molveno) must resolve like the real
# name; otherwise the territory stays unset and the user gets asked again
# right after having confirmed it.
_FUZZY_MIN_LENGTH = 5
_FUZZY_MIN_RATIO = 0.84


def _name_words(text: str) -> List[str]:
    return [w for w in re.split(r"\W+", text) if w]


def territories_named(text: str, allowed: List[str]) -> List[str]:
    """Allowed territories named in `text`: whole-word/phrase matches first;
    only when there are none, close misspellings of a name (single words of
    5+ letters, similarity >= 0.84, so "Moleno" -> Molveno but "molto" is
    not). Every distinct match is returned so callers can treat 2+ as
    ambiguous."""
    normalized = _norm(text)
    if not normalized:
        return []
    exact = [
        t for t in allowed if re.search(rf"\b{re.escape(_norm(t))}\b", normalized)
    ]
    if exact:
        return exact

    words = [w for w in _name_words(normalized) if len(w) >= _FUZZY_MIN_LENGTH]
    fuzzy = []
    for territory in allowed:
        candidates = [w for w in _name_words(_norm(territory)) if len(w) >= _FUZZY_MIN_LENGTH]
        if any(
            abs(len(word) - len(cand)) <= 2
            and difflib.SequenceMatcher(None, word, cand).ratio() >= _FUZZY_MIN_RATIO
            for word in words
            for cand in candidates
        ):
            fuzzy.append(territory)
    return fuzzy


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

    return territories_named(text, allowed)


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
        mentioned = territories_named(last.content, allowed)
        if len(mentioned) == 1:
            state.territory = mentioned[0]
            return True
    return False


def territory_question(allowed: List[str]) -> str:
    options = "\n".join(
        f"{i}. {display_territory(territory)}"
        for i, territory in enumerate(allowed, start=1)
    )
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
    mentioned = territories_named(last.content, state.allowed_territories)
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


# Territorial-index questions ("l'indice di ricettività di Molveno") name a
# MUNICIPALITY: the indexes cover every municipality regardless of the active
# territory (the digital-twin context), so such a mention must not switch it.
_INDEX_QUESTION_RE = re.compile(
    r"\b(indic[ei]|indicator[ei]|index|indexes|indices|"
    r"ricettivit\w*|turisticit\w*|stagionalit\w*|"
    r"densit\w* (?:turistic\w*|antropic\w*)|carico antropico|"
    r"turismo non intercettato|mobilit\w* in (?:ingresso|uscita)|"
    r"intra ambito|centralit\w*|mercati? di provenienza|"
    r"distanza media turisti|consumi (?:elettric\w*|di gas|gas))\b"
)
# Wording that explicitly asks to change the working context.
_SWITCH_INTENT_RE = re.compile(
    r"\b(contesto|territorio|cambia\w*|passa\w*|passiamo|lavor\w+|"
    r"spostiamo|spostarci|torna\w*|torniamo|switch|change|work on|go back)\b"
)


def is_territorial_index_question(text: str) -> bool:
    """True when the message is about territorial indexes and does not
    explicitly ask to change context (e.g. 'passa a Fazzon')."""
    normalized = _norm(text)
    return bool(
        _INDEX_QUESTION_RE.search(normalized)
        and not _SWITCH_INTENT_RE.search(normalized)
    )


def switch_territory_if_requested(state: AgentState) -> Optional[str]:
    """At the start of a fresh user turn: if the user names a different
    allowed territory than the session's current one, switch to it and drop
    the old territory's data. Returns the previous territory when a switch
    happened, else None.

    In integrated mode, an explicit territory in the user's request may
    override the territory captured from the host page for this request.
    A territory not in allowed_territories is never accepted."""
    last = state.get_last_user_message()
    if last is not None and is_territorial_index_question(last.content):
        return None
    target = mentioned_territory(state)
    if not target or target == state.territory:
        return None
    previous = state.territory
    state.territory = target
    reset_territory_scoped_state(state)
    return previous


def territory_switch_note(state: AgentState) -> str:
    """Prompt text describing the latest territory switch, or "" if the
    session never switched. Distinguishes a switch made at the start of THIS
    turn (the user's request has just been carried out) from an earlier one,
    so the model never answers "the context is already X" for a switch it
    has itself just made."""
    switch = state.cognitive.territory_switch
    if not switch or not switch.get("from") or not switch.get("to"):
        return ""
    previous = display_territory(switch["from"])
    current = display_territory(switch["to"])
    if switch.get("this_turn"):
        return (
            f"The territory was switched at the start of THIS turn, at the "
            f"user's request: it was {previous} and it is now {current}. If "
            f"the user asked to change context, that change has JUST been made "
            f"— confirm it and name both (e.g. \"Ho cambiato contesto: ora "
            f"lavoriamo su {current} (prima eravamo su {previous}).\"). Never "
            f"say the context \"is already\" {current}."
        )
    return (
        f"Earlier in this conversation the territory was switched from "
        f"{previous} to {current} at the user's request: everything before "
        f"that switch concerned {previous}; the current context is {current}."
    )


# Territory-agnostic frontend route: territorial indicators (see the
# navigation guideline in prompts/react_guidelines.py).
_INDEX_ROUTE = "/indici"
# Same-app Markdown links in an answer: "[text](/path...)". Absolute URLs
# (web-search sources, https://...) never start with "/" so they don't match.
_SAME_APP_LINK_RE = re.compile(r"\]\((/[^)\s]*)\)")
SIGNAL_TERRITORY_NONE = "none"
# Page where the user selects the territory by hand (same-app route).
TERRITORY_SELECTION_ROUTE = "/problems"


def _is_index_route(path: str) -> bool:
    return path == _INDEX_ROUTE or path.startswith(
        (_INDEX_ROUTE + "/", _INDEX_ROUTE + "?", _INDEX_ROUTE + "#")
    )


def analyze_page_links(state: AgentState, answer: str) -> tuple[Optional[str], bool]:
    """Returns (signal_territory, territory_conflict) for a final answer.

    Only the internal (integrated) chatbot emits same-app page links, so any
    other session gets (None, False). Links are classified as:
      - territorial indicators (/indici): territory-agnostic;
      - problems / proposals / scenarios pages: territory-scoped.

    The path of a link does not carry its territory, so the territory a link
    belongs to is the one the request is about: the single territory the user
    named in the request, else the session's current territory. Outcome:
      - no same-app link                          -> (None, False)
      - only /indici links                        -> ("none", False)
      - territory-scoped links, ONE territory     -> (that territory, False);
        an /indici link next to them does not change this
      - territory-scoped links, request names 2+
        territories (or none is set)              -> (None, True): the links
        cannot be tied to one territory, so the caller must ask the user to
        select the territory manually first (see territory_conflict_note).
    """
    if not state.integrated_mode or not answer:
        return None, False
    paths = _SAME_APP_LINK_RE.findall(answer)
    if not paths:
        return None, False
    scoped = [p for p in paths if not _is_index_route(p)]
    if not scoped:
        return SIGNAL_TERRITORY_NONE, False

    named = territories_named(effective_user_request(state), state.allowed_territories)
    involved = set(named) if named else {state.territory}
    if len(involved) == 1:
        (territory,) = involved
        if is_valid_territory(state, territory):
            return territory, False
    return None, True


def territory_conflict_note(state: AgentState) -> str:
    """Text appended to an answer whose page links span several territories:
    the user must first select the territory by hand, then use the links."""
    if str(state.user_lang).lower().startswith("it"):
        return (
            "Le pagine richieste riguardano territori diversi. Per aprirle, "
            f"imposta prima manualmente il territorio nella pagina "
            f"[Problemi]({TERRITORY_SELECTION_ROUTE}), poi usa i link qui sopra."
        )
    return (
        "The requested pages belong to different territories. To open them, "
        f"first set the territory manually on the [Problems]({TERRITORY_SELECTION_ROUTE}) "
        "page, then use the links above."
    )


def effective_user_request(state: AgentState) -> str:
    """The request the agent is working on. Normally the user's last message;
    but right after the user answered the territory question ("2") that
    message only carries the answer, and the request to carry on with is the
    one that was pending when the question was asked. Without this the model
    treats "2" as a new request (or as a pick from some list in the data)."""
    resume = state.cognitive.territory_resume
    if resume and resume.get("request"):
        return resume["request"]
    last = state.get_last_user_message()
    return last.content if last is not None else ""


def territory_resume_note(state: AgentState) -> str:
    """Prompt text for the turn that resumes after the territory question."""
    resume = state.cognitive.territory_resume
    if not resume or not resume.get("request"):
        return ""
    return (
        f"The user's latest message (\"{resume.get('answer', '')}\") ONLY answered "
        f"the territory question: the territory is now "
        f"{display_territory(resume.get('territory', state.territory))}. It is not "
        f"a new request and not a choice from any other list. Carry on with the "
        f"request they made before: \"{resume['request']}\". Do not ask what the "
        f"answer means and do not ask for details they already gave in that request."
    )
