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
# TOOL DEFINITIONS - SYSTEM
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

# =============================================================================
# TOOL DEFINITIONS - DATA RETRIEVAL
# =============================================================================

def create_list_available_problems_tool() -> ToolDefinition:
    """Tool to list all available problems."""
    return ToolDefinition(
        name="list_available_problems",
        description="List all available problems from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches and displays all available problems. "
        ),
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
        requires_context=None,
        requires_confirmation=False,
    )

def create_list_available_proposals_tool() -> ToolDefinition:
    """Tool to list all available proposals."""
    return ToolDefinition(
        name="list_available_proposals",
        description="List all available proposals from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches and displays all available proposals. "
        ),
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
        requires_context=None,
        requires_confirmation=False,
    )

def create_list_available_scenarios_tool() -> ToolDefinition:
    """Tool to list all available scenarios."""
    return ToolDefinition(
        name="list_available_scenarios",
        description="List all available scenarios from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches and displays all scenarios. "
        ),
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
        requires_context=None,
        requires_confirmation=False,
    )

def create_get_context_ids_tool() -> ToolDefinition:
    """Tool to resolve user intent into concrete object IDs using previously fetched list data."""
    return ToolDefinition(
        name="get_context_ids",
        description=(
            "Resolve the user's intent into specific problem, proposal, and/or scenario IDs "
            "by semantically matching the request against previously fetched list data."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Uses LLM reasoning to match the user's natural-language request against the full "
            "content of one or more already-fetched lists (list_available_problems, "
            "list_available_proposals, list_available_scenarios). "
            "Returns a structured dict {problems: [...], proposals: [...], scenarios: [...]} "
            "containing only the IDs that are relevant to the request. "
            "Always run the required list tools first so their output is in tool_results, "
            "then call this tool to extract the relevant IDs before fetching details."
        ),
        parameters=[
            ToolParameter(
                name="user_intent",
                description=(
                    "The user's original request or intent, verbatim or lightly paraphrased. "
                    "Used as the matching target against the list data."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="source_tools",
                description=(
                    "List of tool result keys (from tool_results) whose data should be searched. "
                    "Valid values: 'list_available_problems', 'list_available_proposals', "
                    "'list_available_scenarios'. Include only the types needed to answer the request."
                ),
                type="array",
                required=True,
                schema={"items": {"type": "string"}},
            ),
        ],
        output_description=(
            "Dict with keys 'problems', 'proposals', 'scenarios', each a list of matching IDs "
            "(empty list when that type is not relevant)."
        ),
        tags=["data", "read-only", "navigation", "resolution"],
        requires_context=None,
        requires_confirmation=False,
    )


def create_get_context_tool() -> ToolDefinition:
    """Tool to retrieve detailed information about current context."""
    return ToolDefinition(
        name="get_context_details",
        description="Get full details about the current context, including all related problems, proposals, and scenarios",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Retrieves full details for the current context, fetching all associated "
            "problems, proposals, and scenarios with their properties and relationships."
        ),
        parameters=[],  # No parameters — operates on state.cognitive.current_context directly
        output_description="Dictionary with retrieved details for all problems, proposals, and scenarios in the current context",
        tags=["data", "read-only"],
        requires_context=None,
        requires_confirmation=False,
    )

def create_interact_with_context_tool() -> ToolDefinition:
    """Tool to answer questions about the current context data."""
    return ToolDefinition(
        name="interact_with_context",
        description="Answer questions about the current problem, proposal, or scenario data",
        category=ToolCategory.INTERACTION,
        long_description=(
            "Allows the agent to view and analyze the active context data. "
            "Must be preceded by get_context_details at some point in the conversation. "
            "Use to answer specific questions or request analysis on retrieved data."
        ),
        parameters=[
            ToolParameter(
                name="query",
                description="Specific question or analysis request about the context data",
                type="string",
                required=True,
            ),
        ],
        output_description="Answer or analysis based on the retrieved context data",
        tags=["interaction", "read-only"],
        requires_context=None,
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
        create_list_available_problems_tool(),
        create_list_available_proposals_tool(),
        create_list_available_scenarios_tool(),

        create_get_context_ids_tool(),
        create_get_context_tool(),
        
        create_interact_with_context_tool(),
    ]


def get_agent_tools_by_category(category: ToolCategory) -> List[ToolDefinition]:
    """Get agent tools filtered by category."""
    all_tools = get_all_agent_tools()
    return [tool for tool in all_tools if tool.category == category]
