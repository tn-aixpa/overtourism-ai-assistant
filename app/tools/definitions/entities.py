"""Entity (problem / proposal / scenario) retrieval tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory
from app.utils.entity_lists import ENTITY_TYPES


def create_list_available_entities_tool() -> ToolDefinition:
    """One listing tool for problems, proposals and scenarios.

    These used to be three zero-argument tools returning the same shape
    (ids + names from one backend GET each). A single tool lets the model
    fetch several kinds in one step (e.g. "which problems and scenarios do
    we have?", or a proposal's parent problem list together with the
    proposals) instead of one ReAct iteration per kind, and removes the
    need for every route sub-group to carry its own copy.
    """
    return ToolDefinition(
        name="list_available_entities",
        description=(
            "List the problems, proposals and/or scenarios available on the "
            "platform (ids, names and relationships)"
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches the lists of existing problems, proposals and/or scenarios "
            "from the backend in a single call. Pass entity_types to fetch only "
            "what is needed — e.g. ['problems', 'proposals'] when the user asks "
            "about both, or ['problems'] to find the parent of a new proposal. "
            "Omit it to fetch all three. This is the first step for resolving an "
            "item the user refers to by name: follow it with get_context_ids to "
            "pick the matching id(s)."
        ),
        parameters=[
            ToolParameter(
                name="entity_types",
                description=(
                    "Which lists to fetch. Any of: "
                    + ", ".join(f"'{t}'" for t in ENTITY_TYPES)
                    + ". Omit to fetch all of them."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string", "enum": list(ENTITY_TYPES)}},
            ),
        ],
        output_description=(
            "Dictionary keyed by entity type ('problems', 'proposals', 'scenarios'), "
            "each a list of {<type>_id, name, ...} items; only the requested types "
            "are present."
        ),
        tags=["data", "read-only", "navigation"],
        agent_tier="executor",
        requires_territory=True,
        allowed_modes=("standalone", "internal"),
    )


def _create_legacy_list_tool(name: str, label: str) -> ToolDefinition:
    """Compatibility shim for older code paths that still ask for a single-purpose list tool."""
    return ToolDefinition(
        name=name,
        description=f"List the available {label} on this platform",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            f"Legacy alias for list_available_entities that fetches the {label} list "
            "for compatibility with existing reasoner prompts and persisted state."
        ),
        parameters=[],
        output_description=f"List of available {label} records",
        tags=["data", "read-only", "navigation"],
        agent_tier="executor",
        requires_territory=True,
        allowed_modes=("standalone", "internal"),
    )


def create_list_available_problems_tool() -> ToolDefinition:
    return _create_legacy_list_tool("list_available_problems", "problems")


def create_list_available_proposals_tool() -> ToolDefinition:
    return _create_legacy_list_tool("list_available_proposals", "proposals")


def create_list_available_scenarios_tool() -> ToolDefinition:
    return _create_legacy_list_tool("list_available_scenarios", "scenarios")


__all__ = [
    "create_list_available_entities_tool",
    "create_list_available_problems_tool",
    "create_list_available_proposals_tool",
    "create_list_available_scenarios_tool",
]
