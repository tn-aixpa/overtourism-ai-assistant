"""
Prompt for the top-level/second-level topic router (see
app.agent.nodes.router.top_level_router_node).

This is a single lightweight classification call, deliberately kept
separate from react_step's own reasoning prompt: its only job is "which
slice of the tool registry is relevant to this message", not "which tool
and arguments". Scoping the tool list down before react_step runs is the
whole point — react_step keeps doing the fine-grained reasoning within
whatever slice this call selects.
"""

import json
import logging

from app.agent.state import AgentState
from app.agent.nodes import route_groups as rg
from app.utils.llm import llm_interaction, format_messages

logger = logging.getLogger(__name__)


def _format_top_level_options() -> str:
    lines = []
    for key, label in rg.TOP_LEVEL_LABELS.items():
        lines.append(f'- "{key}": {label}')
        sub_options = rg.sublevel_options(key)
        if sub_options:
            # Always show sub-areas nested under their domain, regardless
            # of whether this session already has a persisted route: a
            # message can be specific enough to resolve top_level AND
            # second_level in this same call (e.g. "quali problemi ci
            # sono?" -> location/problem in one shot) and the model can
            # only do that if it's shown the sub-options up front, not
            # only after a route is already persisted. Without this, even
            # an unambiguous message always cost an extra clarification
            # round-trip to resolve the second level.
            for sub_key, sub_label in sub_options.items():
                lines.append(f'    - "{sub_key}": {sub_label}')
    return "\n".join(lines)


def classify_route(
    state: AgentState,
    current_top_level: str | None,
    current_second_level: str | list[str] | None,
) -> dict:
    """
    Decide top-level (and, where relevant, second-level) routing for the
    current message, one call per turn.

    Returns a dict with keys:
      - "top_level": one of rg.TOP_LEVEL_LABELS keys, or "unclear"
      - "topic_changed": bool — true if this message no longer belongs to
        `current_top_level`/`current_second_level` (irrelevant if there was
        no current route yet)
      - "second_level": a sub-group key, a LIST of sub-group keys (when the
        message confidently names more than one sub-area of the resolved
        top_level at once — e.g. "problemi e scenari" -> ["problem",
        "scenario"]), "unclear", or None if the resolved top_level has no
        sub-levels
    On any parsing failure, returns a dict with every field "unclear" /
    False so the caller falls back to asking the user directly rather than
    silently guessing.
    """

    message = (state.get_last_user_message() or "").content
    history = state.get_reasoning_context()
    if history and history[-1].get("content") == message:
        history = history[:-1]
    history_block = format_messages(history) if history else "None"

    current_second_display = (
        ", ".join(current_second_level)
        if isinstance(current_second_level, list)
        else current_second_level
    )
    current_route_block = (
        f'- top_level: "{current_top_level}"\n'
        f'- second_level: "{current_second_display}"'
        if current_top_level
        else "None yet — this session hasn't been routed to a domain."
    )

    prompt = f"""
You are the topic router for an assistant on a tourism-management digital
twin platform. Your ONLY job is to decide which of four domains the user's
message belongs to — you do NOT answer the question and you do NOT pick a
specific tool.

============================================================
TOP-LEVEL DOMAINS (sub-areas nested where a domain has them)
============================================================
{_format_top_level_options()}

If the message is specific enough to tell which sub-area it's about too
(e.g. "quali problemi ci sono?" -> top_level "location", second_level
"problem"), resolve BOTH in this same call — don't leave second_level
"unclear" just because you're also deciding top_level for the first time;
the two are independent judgments about the same message, not sequential
steps that need separate turns. Only leave second_level "unclear" when the
message really doesn't indicate a specific sub-area (e.g. "dimmi qualcosa
sulla mia località" — some LOCATION content, but no specific sub-area).

If the message confidently names MORE THAN ONE sub-area of the SAME
top-level domain (e.g. "quali problemi e scenari sono disponibili?" is
"location" with both "problem" and "scenario"), return "second_level" as a
JSON ARRAY of every sub-area key it names, not just the first one — do not
pick only one and do not fall back to "unclear" just because there's more
than one. Only use an array when each named sub-area is individually
unambiguous; if even one part is vague, use "unclear" for the whole field
instead of guessing which sub-areas were meant.

If the message clearly fits more than one top-level domain heuristically,
prefer the most specific: e.g. a question about a named territorial index
is "indexes", not "system_info", even though indexes are technically part
of the system.

Within "indexes", distinguish requests about existing index data from
methodology questions. Requests to define, design, construct, choose
variables for, interpret, or validate a new territorial index belong to
second_level "index_methodology". Requests for which indexes exist, their
available periods, maps, or charts belong to index_list, index_map, or
index_plot respectively. Numeric questions about index values — the value
of an index for one or more named municipalities, or which/how many
municipalities are above or below a given value — belong to index_query,
even when they refer to what a map shows. For index_methodology, use top_level "indexes".

============================================================
CURRENT ROUTE FOR THIS SESSION
============================================================
{current_route_block}

If the new message is a natural continuation of the current route (e.g.
still talking about the same problem/proposal/scenario/index, a follow-up,
a confirmation, providing missing details you'd expect for that domain),
set "topic_changed" to false and you do not need to re-decide top_level
confidently — the caller will keep the current route. Only set
"topic_changed" to true if the message is clearly about a different one of
the four domains above (or is ambiguous/unclear even considering the
current route).

============================================================
OUTPUT FORMAT
============================================================
Return ONLY ONE JSON object, no markdown, no extra text:

{{
  "top_level": "<one of: system_info, location, indexes, general, unclear>",
  "topic_changed": <true or false>,
  "second_level": "<sub-area key for the resolved top_level, a JSON array
     of several sub-area keys if the message confidently names more than
     one (see rule above), null if top_level has no sub-areas, or
     \\"unclear\\" if top_level has sub-areas but you cannot tell which one>"
}}

Rules:
- A bare greeting ("ciao", "hello", "hi"), small talk, or a vague opener
  with no specific topic ("cosa puoi fare?", "help", "what can you do",
  "come funziona?") is "system_info", NOT "unclear" — resolve it
  confidently and proactively rather than asking the user to pick a
  domain for something this generic. Asking a menu for "ciao" reads as
  making the user do the work the assistant should default to; jumping
  straight into system_info (which naturally leads to a capabilities
  overview) is the more helpful, proactive default.
- "unclear" for top_level otherwise ONLY if the message genuinely could
  belong to more than one domain, or none — do not default to "unclear"
  just because the message is short (e.g. "yes", "the parking one", plain
  follow-ups answering a question you asked are NOT unclear if the
  current route makes the intent obvious).
- A follow-up that asks whether concrete instances/records already exist
  on the platform ("are there scenarios/problems/proposals already
  defined?", "what problems exist?", "show me the current X") is ALWAYS
  "location" (or "indexes" for index data) — set "topic_changed" to true
  for this, even if the current route is "system_info" and even if the
  previous turn discussed the same concept abstractly. Explaining what a
  scenario *is* (system_info) and asking whether scenarios *already
  exist* (location) are different domains that happen to share
  vocabulary; a request for real platform data is a topic change even
  when the noun stays the same.
- "second_level" must be null when top_level is "system_info" or "general"
  (they have no sub-areas).
- Never invent a key that isn't listed above.

============================================================
CONTEXT
============================================================
Conversation so far:
{history_block}

New user message:
"{message}"

Return ONLY valid JSON.
"""

    raw = llm_interaction(state, prompt, lightweight_llm=True)
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        parsed = json.loads(cleaned)
        second_level = parsed.get("second_level")
        if isinstance(second_level, list):
            # Keep only well-formed entries — a stray non-string in the
            # array shouldn't crash routing, just get dropped like any
            # other invalid key does downstream (route_groups filters
            # against each domain's actual sub-group keys anyway).
            second_level = [s for s in second_level if isinstance(s, str)]
        return {
            "top_level": parsed.get("top_level", "unclear"),
            "topic_changed": bool(parsed.get("topic_changed", False)),
            "second_level": second_level,
        }
    except Exception as e:
        logger.warning(
            f"Failed to parse route classification response: {e} | raw={raw!r}"
        )
        return {
            "top_level": "unclear",
            "topic_changed": True,
            "second_level": "unclear",
        }
