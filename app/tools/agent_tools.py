"""
Tool definitions for the agentic system.

Converts existing workflows into reusable, decision-based tools that the agent can invoke.
"""

from typing import List
import logging

from app.tools.tool_schema import (
    ToolDefinition, 
    ToolParameter, 
    ToolCategory,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

def create_get_system_capabilities_tool() -> ToolDefinition:
    """Tool to retrieve system description and capabilities."""
    return ToolDefinition(
        name="get_system_capabilities",
        description="Retrieve a description of the system and its capabilities",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Returns a description of the system, its core concepts (problems, proposals, scenarios), "
            "allowed operations per context level, and which tools are available in each context. "
            "Call this at startup or whenever clarification about system capabilities is needed."
        ),
        parameters=[],
        output_description="System description, context rules, and available tools per context",
        tags=["data", "read-only", "system", "navigation"],
        requires_context=None,
        requires_confirmation=False,
    )

def create_list_available_items_tool() -> ToolDefinition:
    """Tool to list all available problems."""
    return ToolDefinition(
        name="list_available_items",
        description="List all available problems, proposals and scenarios from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches and displays all available problems, proposals, and scenarios. "
            "Shows relationships between problems and their proposals, and proposals with their scenarios."
        ),
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
        requires_context=None,
        requires_confirmation=False,
    )


def create_get_context_tool() -> ToolDefinition:
    """Tool to retrieve detailed information about current context."""
    return ToolDefinition(
        name="get_context_details",
        description="Get detailed information about problems, proposals, or scenarios",
        category=ToolCategory.CONTEXT_MANAGEMENT,
        long_description=(
            "Retrieves full details for specified problems, proposals, or scenarios "
            "including their properties, editable fields, and relationships."
        ),
        parameters=[
            ToolParameter(
                name="context_type",
                description="Type of context to retrieve (problem, proposal, or scenario)",
                type="string",
                required=True,
                enum_values=["problem", "proposal", "scenario"],
            ),
            ToolParameter(
                name="context_ids",
                description="List of IDs to retrieve",
                type="array",
                required=True,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="extract_editable",
                description="Whether to extract editable field information",
                type="boolean",
                required=False,
                default=True,
            ),
        ],
        output_description="Dictionary with retrieved details and editable field information",
        tags=["data", "read-only"],
        requires_context=None,
        requires_confirmation=False,
    )


def create_set_active_context_tool() -> ToolDefinition:
    """Tool to set the active working context."""
    return ToolDefinition(
        name="set_active_context",
        description="Set the active problem, proposal, or scenario context",
        category=ToolCategory.CONTEXT_MANAGEMENT,
        long_description=(
            "Changes the active context that the agent is working with. "
            "This context is used for operations that need a target (like creating proposals for a problem)."
        ),
        parameters=[
            ToolParameter(
                name="context_type",
                description="Type of context to set as active",
                type="string",
                required=True,
                enum_values=["problem", "proposal", "scenario"],
            ),
            ToolParameter(
                name="context_id",
                description="ID of the item to set as active context",
                type="string",
                required=True,
            ),
        ],
        output_description="Confirmation that context has been set",
        tags=["management"],
        requires_context=None,
        requires_confirmation=False,
    )


def create_extract_problem_tool() -> ToolDefinition:
    """Tool to extract problem information from user input."""
    return ToolDefinition(
        name="extract_problem_details",
        description="Extract and structure problem information from user input",
        category=ToolCategory.PROBLEM_MANAGEMENT,
        long_description=(
            "Analyzes user input to extract structured problem information including "
            "title, description, objectives, available subsystems, and related data. "
            "Returns extracted information for user confirmation before creation."
        ),
        parameters=[
            ToolParameter(
                name="user_input",
                description="User's description of the problem",
                type="string",
                required=True,
            ),
        ],
        output_description="Structured problem information ready for confirmation",
        tags=["extraction", "problem"],
        requires_context=None,
        requires_confirmation=True,  # User must confirm before creation
    )


def create_create_problem_tool() -> ToolDefinition:
    """Tool to create a new problem instance."""
    return ToolDefinition(
        name="create_problem",
        description="Create a new problem instance in the backend",
        category=ToolCategory.PROBLEM_MANAGEMENT,
        long_description=(
            "Creates a new problem with the provided details. "
            "Usually follows extraction and user confirmation."
        ),
        parameters=[
            ToolParameter(
                name="problem_title",
                description="Title of the problem",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="problem_description",
                description="Detailed description of the problem",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="objectives",
                description="List of objectives or goals",
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="available_subsystems",
                description="Available subsystems or groups for this problem",
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="additional_data",
                description="Additional metadata or links",
                type="object",
                required=False,
            ),
        ],
        output_description="Created problem instance with ID",
        tags=["creation", "problem"],
        requires_context=None,
        requires_confirmation=False,
    )


def create_extract_proposal_tool() -> ToolDefinition:
    """Tool to extract proposal information from user input."""
    return ToolDefinition(
        name="extract_proposal_details",
        description="Extract and structure proposal information from user input",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description=(
            "Analyzes user input to extract structured proposal information for an active problem. "
            "Includes title, description, connected scenarios, and other proposal details."
        ),
        parameters=[
            ToolParameter(
                name="user_input",
                description="User's description of the proposal",
                type="string",
                required=True,
            ),
        ],
        output_description="Structured proposal information ready for confirmation",
        tags=["extraction", "proposal"],
        requires_context=None,  # "problem" if it requires active problem context
        requires_confirmation=True,
    )


def create_create_proposal_tool() -> ToolDefinition:
    """Tool to create a new proposal instance."""
    return ToolDefinition(
        name="create_proposal",
        description="Create a new proposal instance for the active problem",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description=(
            "Creates a new proposal linked to the active problem. "
            "Usually follows extraction and user confirmation."
        ),
        parameters=[
            ToolParameter(
                name="proposal_title",
                description="Title of the proposal",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="proposal_description",
                description="Detailed description of the proposal",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="connected_scenarios",
                description="Related scenario IDs",
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="additional_data",
                description="Additional metadata",
                type="object",
                required=False,
            ),
        ],
        output_description="Created proposal instance with ID",
        tags=["creation", "proposal"],
        requires_context=None,  # "problem" if it requires active problem context
        requires_confirmation=False,
    )


def create_extract_scenario_tool() -> ToolDefinition:
    """Tool to extract scenario information from user input."""
    return ToolDefinition(
        name="extract_scenario_details",
        description="Extract and structure scenario information from user input",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Analyzes user input to extract structured scenario information for an active proposal. "
            "Includes scenario name, description, model values, and validation."
        ),
        parameters=[
            ToolParameter(
                name="user_input",
                description="User's description of the scenario",
                type="string",
                required=True,
            ),
        ],
        output_description="Structured scenario information with validated model values",
        tags=["extraction", "scenario"],
        requires_context=None,  # "proposal" if it requires active proposal context
        requires_confirmation=True,
    )


def create_create_scenario_tool() -> ToolDefinition:
    """Tool to create a new scenario instance."""
    return ToolDefinition(
        name="create_scenario",
        description="Create a new scenario instance for the active proposal",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Creates a new scenario linked to the active proposal. "
            "Usually follows extraction and user confirmation."
        ),
        parameters=[
            ToolParameter(
                name="scenario_name",
                description="Name of the scenario",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="scenario_description",
                description="Description of the scenario",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="model_values",
                description="Input values for the scenario model",
                type="object",
                required=True,
            ),
            ToolParameter(
                name="additional_data",
                description="Additional metadata",
                type="object",
                required=False,
            ),
        ],
        output_description="Created scenario instance with ID",
        tags=["creation", "scenario"],
        requires_context=None,  # "proposal" if it requires active proposal context
        requires_confirmation=False,
    )


def create_interact_with_context_tool() -> ToolDefinition:
    """Tool to interact with the current context (view, edit, analyze)."""
    return ToolDefinition(
        name="interact_with_context",
        description="Interact with the current problem, proposal, or scenario",
        category=ToolCategory.INTERACTION,
        long_description=(
            "Allows the agent to view, edit, or perform analysis on the active context. "
            "Can query specific aspects or trigger backend analysis."
        ),
        parameters=[
            ToolParameter(
                name="interaction_type",
                description="Type of interaction",
                type="string",
                required=True,
                enum_values=["view", "edit", "analyze", "export"],
            ),
            ToolParameter(
                name="query",
                description="Specific query or request",
                type="string",
                required=False,
            ),
            ToolParameter(
                name="modifications",
                description="Data modifications (if interaction_type is 'edit')",
                type="object",
                required=False,
            ),
        ],
        output_description="Result of the interaction",
        tags=["interaction"],
        requires_context=None,  # TODO: check if needs to be
        requires_confirmation=False,
    )


# =============================================================================
# TOOL COLLECTION
# =============================================================================

def get_all_agent_tools() -> List[ToolDefinition]:
    """Get all available agent tools."""
    return [
        # System
        create_get_system_capabilities_tool(),

        # Data retrieval
        create_list_available_items_tool(),
        create_get_context_tool(),
        
        # Context management
        create_set_active_context_tool(),
        
        # Problem management
        create_extract_problem_tool(),
        create_create_problem_tool(),
        
        # Proposal management
        create_extract_proposal_tool(),
        create_create_proposal_tool(),
        
        # Scenario management
        create_extract_scenario_tool(),
        create_create_scenario_tool(),
        
        # Interaction
        create_interact_with_context_tool(),
    ]


def get_agent_tools_by_category(category: ToolCategory) -> List[ToolDefinition]:
    """Get agent tools filtered by category."""
    all_tools = get_all_agent_tools()
    return [tool for tool in all_tools if tool.category == category]
