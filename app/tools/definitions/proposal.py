"""Proposal tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolCategory
from app.utils.backend_entities_parameters import (
    PROPOSAL_PARAMETERS,
)


def create_new_proposal_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_proposal",
        description="Create a new proposal linked to an existing problem",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description=(
            "Registers a new Proposal for a given Problem in the platform. "
            "A Proposal represents a possible strategy to address the problem. "
        ),
        parameters=PROPOSAL_PARAMETERS,
        output_description="Acknowledgement of successful creation or request for more details",
        tags=["write", "proposal"],
        agent_tier="executor",
        requires_territory=True,
        allowed_roles=("admin", "multieditor", "editor"),
        allowed_modes=("standalone", "internal"),
    )


def edit_proposal_tool() -> ToolDefinition:
    return ToolDefinition(
        name="edit_proposal",
        description="Edit an existing proposal",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description="Edit a one or more attributes of a Proposal in the platform.",
        parameters=PROPOSAL_PARAMETERS,
        output_description="Acknowledgement of successful edit or request for more details",
        tags=["write", "proposal"],
        agent_tier="executor",
        requires_territory=True,
        allowed_roles=("admin", "multieditor", "editor"),
        allowed_modes=("standalone", "internal"),
    )


def delete_proposal_tool() -> ToolDefinition:
    return ToolDefinition(
        name="delete_proposal",
        description="Delete a proposal",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description="Delete a Proposal in the platform.",
        parameters=[],
        output_description="Acknowledgement of successful deletetion or request for more details",
        tags=["write", "proposal"],
        agent_tier="executor",
        requires_territory=True,
        allowed_roles=("admin", "multieditor", "editor"),
        allowed_modes=("standalone", "internal"),
    )


__all__ = [
    "create_new_proposal_tool",
    "edit_proposal_tool",
    "delete_proposal_tool",
]
