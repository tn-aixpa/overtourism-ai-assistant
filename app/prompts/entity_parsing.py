import logging
import json
from typing import Dict, Any, List


from app.agent.state import AgentState
from app.utils.llm import llm_interaction, format_messages

logger = logging.getLogger(__name__)


def get_relatet_context_ids(
    state: AgentState,
    user_intent: str,
    source_tools: list,
):

    # ------------------------------------------------------------------ #
    # 1. Collect the raw list data from tool_results
    # ------------------------------------------------------------------ #
    tool_results = state.cognitive.tool_results

    # Build a mapping  entity_type -> raw data, tolerating key variants
    # (e.g. the selector might store them as "list_available_problems" or
    #  with a collision suffix like "list_available_problems__1").
    def _find_result(key_prefix: str) -> Any:
        """Return the first tool_results value whose key starts with key_prefix."""
        for k, v in tool_results.items():
            if k == key_prefix or k.startswith(key_prefix + "__"):
                return v
        return None

    sections: Dict[str, Any] = {}
    for source in source_tools:
        data = _find_result(source)
        if data is None:
            logger.warning(
                f"get_context_ids: source '{source}' not found in tool_results "
                f"(available keys: {list(tool_results.keys())})"
            )
        else:
            sections[source] = data

    if not sections:
        return {
            "success": False,
            "error": (
                "None of the requested source tools have results in tool_results. "
                f"Requested: {source_tools}. "
                f"Available: {list(tool_results.keys())}. "
                "Run the list tools first."
            ),
            "context_ids": {"problems": [], "proposals": [], "scenarios": []},
        }

    sections_block = json.dumps(sections, indent=2, default=str)

    # ------------------------------------------------------------------ #
    # 2. Build prompt
    # ------------------------------------------------------------------ #

    prompt = f"""
You are a semantic matching assistant for a digital twin platform about tourism management.

Your task: given a user intent and a set of object lists fetched from the backend,
identify which objects (by their ID) are relevant to the intent.

Consider ALL fields of each object (name, description, tags, location, relationships, etc.)
when deciding relevance. Be inclusive — if an object is plausibly related, include it.

User intent:
\"{user_intent}\"

Available data (raw API responses, one section per list tool):
{sections_block}

Return ONLY a valid JSON object with exactly these three keys (lists may be empty):
{{
  "problems":  ["<id>", ...],
  "proposals": ["<id>", ...],
  "scenarios": ["<id>", ...]
}}

Do not include any explanation or markdown. Return JSON only.
"""

    return llm_interaction(state, prompt).strip()
