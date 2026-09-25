"""Problem tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolCategory
from app.utils.backend_entities_parameters import (
    PROBLEM_PARAMETERS,
)


def create_list_available_problems_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_available_problems",
        description="List all available problems from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description="Fetches and displays all available problems.",
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
        agent_tier="executor",
        allowed_modes=("standalone", "internal"),
    )


def create_new_problem_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_problem",
        description="Create a new problem in the system",
        category=ToolCategory.PROBLEM_MANAGEMENT,
        long_description=(
            "Registers a new Problem in the platform. "
            "A Problem represents a critical situation or phenomenon to be analyzed "
            "(e.g. overtourism, mobility congestion). "
        ),
        parameters=PROBLEM_PARAMETERS,
        output_description="Acknowledgement of successful creation or request for more details",
        tags=["write", "problem"],
        agent_tier="executor",
        allowed_roles=("admin", "standard"),
        allowed_modes=("standalone", "internal"),
    )


def edit_problem_tool() -> ToolDefinition:
    return ToolDefinition(
        name="edit_problem",
        description="Edit a problem available in the system system",
        category=ToolCategory.PROBLEM_MANAGEMENT,
        long_description="Edit one or more attributes of a Problem in the platform.",
        parameters=PROBLEM_PARAMETERS,
        output_description="Acknowledgement of successful edit or request for more details",
        tags=["write", "problem"],
        agent_tier="executor",
        allowed_roles=("admin", "standard"),
        allowed_modes=("standalone", "internal"),
    )


def delete_problem_tool() -> ToolDefinition:
    return ToolDefinition(
        name="delete_problem",
        description="Delete a problem in the system",
        category=ToolCategory.PROBLEM_MANAGEMENT,
        long_description="Delete a Problem in the platform.",
        parameters=[],
        output_description="Acknowledgement of successful deletion or request for more details",
        tags=["write", "problem"],
        agent_tier="executor",
        allowed_roles=("admin", "standard"),
        allowed_modes=("standalone", "internal"),
    )


__all__ = [
    "create_list_available_problems_tool",
    "create_new_problem_tool",
    "edit_problem_tool",
    "delete_problem_tool",
]
