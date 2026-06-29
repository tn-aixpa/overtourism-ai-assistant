"""
Tool definitions for the agentic system.
"""

from typing import List
import logging

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory

logger = logging.getLogger(__name__)


def create_get_system_capabilities_tool() -> ToolDefinition:
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
    )


def create_list_available_proposals_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_available_proposals",
        description="List all available proposals from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description="Fetches and displays all available proposals.",
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
    )


def create_list_available_scenarios_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_available_scenarios",
        description="List all available scenarios from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description="Fetches and displays all scenarios.",
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
    )


def create_get_context_ids_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_context_ids",
        description=(
            "Resolve the user's intent into specific problem, proposal, and/or scenario IDs "
            "by semantically matching the request against previously fetched list data."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Uses LLM reasoning to match the user's natural-language request against the full "
            "content of one or more already-fetched lists. "
            "Returns a structured dict {problems: [...], proposals: [...], scenarios: [...]} "
            "containing only the IDs that are relevant to the request. "
            "Always run the required list tools first, then call this tool to extract relevant IDs."
        ),
        parameters=[
            ToolParameter(
                name="user_intent",
                description="The user's original request or intent, verbatim or lightly paraphrased.",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="source_tools",
                description=(
                    "List of tool result keys to search. "
                    "Valid values: 'list_available_problems', 'list_available_proposals', "
                    "'list_available_scenarios'."
                ),
                type="array",
                required=True,
                schema={"items": {"type": "string"}},
            ),
        ],
        output_description="Dict with keys 'problems', 'proposals', 'scenarios', each a list of matching IDs.",
        tags=["data", "read-only", "navigation", "resolution"],
    )


def create_get_context_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_context_details",
        description=(
            "Get full details about the current context, including all related problems, "
            "proposals, and scenarios. MUST be called before interact_with_context if context "
            "details have not yet been retrieved in this conversation."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Retrieves full details for the current context, fetching all associated "
            "problems, proposals, and scenarios with their properties and relationships."
        ),
        parameters=[],
        output_description="Dictionary with retrieved details for all items in the current context",
        tags=["data", "read-only"],
    )


def create_interact_with_context_tool() -> ToolDefinition:
    return ToolDefinition(
        name="interact_with_context",
        description="Answer questions about the current problem, proposal, or scenario data",
        category=ToolCategory.INTERACTION,
        long_description=(
            "Allows the agent to view and analyze the active context data. "
            "Must be preceded by get_context_details at some point in the conversation."
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
    )


def get_all_agent_tools() -> List[ToolDefinition]:
    return [
        create_get_system_capabilities_tool(),
        create_list_available_problems_tool(),
        create_list_available_proposals_tool(),
        create_list_available_scenarios_tool(),
        create_get_context_ids_tool(),
        create_get_context_tool(),
        create_interact_with_context_tool(),
    ]
