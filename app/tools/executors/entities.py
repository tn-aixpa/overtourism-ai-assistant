"""Entity (problem / proposal / scenario) retrieval tool implementations."""

from typing import Any, Dict, List, Optional
import logging

from app.agent.state import AgentState
from app.utils.entity_lists import normalize_entity_types

logger = logging.getLogger(__name__)


def execute_list_available_entities(
    state: AgentState,
    entity_types: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute list_available_entities tool.

    Returns ``{"problems": [...], "proposals": [...], "scenarios": [...]}``
    restricted to the requested types. If some (but not all) of the
    requested lists could not be fetched, the rest are still returned and
    the failed types are named under ``"unavailable"`` so the reasoner can
    retry or say so; if none could be fetched, the tool fails.
    """
    from app.tools.executor_backend_tools import (
        get_all_problems,
        get_all_proposals,
        get_all_scenarios,
    )

    requested = normalize_entity_types(entity_types)
    logger.info(f"Executing list_available_entities tool for {requested}")

    fetchers = {
        "problems": get_all_problems,
        "proposals": get_all_proposals,
        "scenarios": get_all_scenarios,
    }

    result: Dict[str, Any] = {}
    unavailable: List[str] = []
    for entity_type in requested:
        try:
            result[entity_type] = fetchers[entity_type].invoke(
                {"territory": state.territory}
            )
        except Exception:
            # Backend detail stays in the logs; the reasoner only needs to
            # know which list is missing.
            logger.exception(f"Could not fetch the list of {entity_type}")
            unavailable.append(entity_type)

    if not result:
        raise RuntimeError(f"Could not retrieve the list of {', '.join(requested)}")
    if unavailable:
        result["unavailable"] = unavailable

    return result


EXECUTORS = {
    "list_available_entities": execute_list_available_entities,
}
