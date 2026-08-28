"""System Utility tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def execute_lookup_glossary(
    state: AgentState,
    query: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute lookup_glossary tool.

    Performs a case-insensitive fuzzy search over the GLOSSARY dict in config.
    Matches the query tokens against: term name, aliases, and related_terms.
    Returns all matching entries with their full detail.
    """
    from app.utils.knowledge import GLOSSARY

    logger.info(f"Executing lookup_glossary | query='{query}'")

    tokens = [t.strip().lower() for t in query.split() if t.strip()]
    if not tokens:
        return {
            "success": False,
            "error": "Empty query — please provide at least one search term.",
            "matches": [],
        }

    matches = {}
    for entry in GLOSSARY:
        term = entry["term"]
        # Build a flat list of strings to match against. "it" is included
        # here (unlike in app.knowledge's text-matcher) because this
        # tool is meant to resolve a user's query — including one phrased in
        # Italian — back to the right entry, not to decide what to generate.
        searchable = (
            [term]
            + entry.get("aliases", [])
            + entry.get("related_terms", [])
            + entry.get("it", [])
        )
        searchable_lower = " ".join(s.lower() for s in searchable)

        if any(tok in searchable_lower for tok in tokens):
            matches[term] = entry

    if not matches:
        return {
            "success": True,
            "message": (
                f"No glossary entries found for '{query}'. "
                "Try broader keywords or ask about a specific platform concept."
            ),
            "matches": [],
        }

    # Format for readability in the output generator
    formatted = []
    for term, entry in matches.items():
        formatted.append(
            {
                "term": term,
                "definition": entry["definition"],
                "aliases": entry.get("aliases", []),
                "related_terms": entry.get("related_terms", []),
                "examples": entry.get("examples", []),
                "it": entry.get("it", []),
            }
        )

    logger.info(f"lookup_glossary found {len(formatted)} match(es) for '{query}'")

    return {
        "success": True,
        "query": query,
        "matches": formatted,
    }


def execute_general_question_response(
    state: AgentState,
    query: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute general_question_response tool.

    Answers a general question with a free-form LLM call — not grounded in
    platform data, the glossary, or any other verified source.

    This tool's ToolDefinition.agent_tier is "exploitative": an unguarded
    tier that (a) requires one-time user consent before a session may use
    it at all (enforced upstream by tool_executor_node's tier-consent gate)
    and (b) determines the response persona/policy generate_answer() below
    uses (see _reasoning_policy in answer_generation.py). Both effects come
    from tool_executor_node bumping state.active_agent to this tool's
    agent_tier before running it — nothing tool-specific needed here.
    """
    from app.prompts.answer_generation import generate_answer

    logger.info(f"Executing general_question_response | query='{query}'")

    answer = generate_answer(state)

    return {
        "success": True,
        "query": query,
        "answer": answer,
    }


def execute_get_system_capabilities(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute get_system_capabilities tool."""
    from app.utils.system_capabilities import SYSTEM_DESCRIPTION

    logger.info("Executing get_system_capabilities tool")

    return {
        "success": True,
        "system_description": SYSTEM_DESCRIPTION,
    }


def execute_get_data_from_link(
    state: AgentState,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute get_data_from_link tool."""
    from app.tools.other_tools import get_data_from_link

    logger.info(f"Executing get_data_from_link for {url}")
    result = get_data_from_link.invoke(
        {
            "url": url,
            "headers": headers,
            "params": params,
        }
    )
    return result


EXECUTORS = {
    "lookup_glossary": execute_lookup_glossary,
    "get_system_capabilities": execute_get_system_capabilities,
    "general_question_response": execute_general_question_response,
    "get_data_from_link": execute_get_data_from_link,
}
