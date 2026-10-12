import logging
import json
from typing import Dict, Any, List

from app.agent.state import AgentState
from app.utils.llm import llm_interaction, format_messages
from app.utils.common import condense_for_matching

logger = logging.getLogger(__name__)


def get_relatet_context_ids(
    state: AgentState,
    user_intent: str,
    listed_entities: Dict[str, List[Any]],
):
    """Ask the LLM which of the already-fetched entities match `user_intent`.

    `listed_entities` maps an entity type ("problems" / "proposals" /
    "scenarios") to its latest fetched list — see
    app.utils.entity_lists.collect_listed_entities, which is what the caller
    uses to build it. Raises ValueError if it is empty (nothing was listed
    yet), with a message the reasoner can act on.
    """

    if not listed_entities:
        raise ValueError(
            "No problem/proposal/scenario list has been fetched yet. "
            "Call list_available_entities first, then get_context_ids."
        )

    # Condense before injecting: matching only needs id/name/description-type
    # fields, not the full raw payload (which can carry large nested extras
    # like scenario evaluation_data). This keeps the prompt bounded
    # regardless of how much data the territory has, instead of growing with
    # the dataset. See app.utils.common.condense_for_matching.
    condensed_sections = {
        entity_type: condense_for_matching(data)
        for entity_type, data in listed_entities.items()
    }
    sections_block = json.dumps(condensed_sections, indent=2, default=str)

    # ------------------------------------------------------------------ #
    # Build prompt
    # ------------------------------------------------------------------ #

    prompt = f"""
You are a semantic matching assistant for a digital twin platform about tourism management.

Your task: given a user intent and a set of object lists fetched from the backend,
identify which objects (by their ID) are relevant to the intent.

Consider the available fields of each object (name, description, tags, location,
relationships, etc.) when deciding relevance — note that bulky/nested fields (e.g.
extended metadata, simulation data) have been stripped out below since they aren't
needed for matching. Be inclusive — if an object is plausibly related, include it.
If the data below mentions additional items not shown in full, and none of the shown
items are a good match, say so in your reasoning rather than guessing.

User intent:
\"{user_intent}\"

Available data (raw API responses, one section per entity type):
{sections_block}

Return ONLY a valid JSON object with exactly these three keys (lists may be empty):
{{
  "problems":  ["<id>", ...],
  "proposals": ["<id>", ...],
  "scenarios": ["<id>", ...]
}}

Do not include any explanation or markdown. Return JSON only.
"""

    return llm_interaction(state, prompt, lightweight_llm=True).strip()
