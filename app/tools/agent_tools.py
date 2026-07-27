"""
Tool definitions for the agentic system.
"""

from typing import List
import logging

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory
from app.utils.backend_entities_parameters import (
    PROBLEM_PARAMETERS,
    PROPOSAL_PARAMETERS,
    SCENARIO_PARAMETERS,
)

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
            "Retrieve the stored information for the current problem, proposal, or scenario, "
            "including descriptions, metadata, relationships, and other textual attributes."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Retrieve the stored information for the current problem, proposal, or scenario, "
            "including descriptions, metadata, relationships, and other textual attributes."
        ),
        parameters=[],
        output_description="Dictionary with retrieved details for all items in the current context",
        tags=["data", "read-only"],
    )


def create_analyze_scenario_results_tool() -> ToolDefinition:
    return ToolDefinition(
        name="analyze_scenario_results",
        description=(
            "Interpret or compare scenario evaluation results, such as metrics, "
            "graphs, indicators, and simulation outputs."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Uses the data previously retrieved by get_context_details to explain "
            "scenario evaluation results. This tool should only be used for requests "
            "about numerical indicators, charts, KPIs, simulation outputs, or "
            "comparisons between scenarios. It is not intended for simply describing "
            "a problem, proposal, or scenario."
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


def create_summary_generation_tool() -> ToolDefinition:
    """Internal-only variant of analyze_scenario_results.

    `enabled=False` keeps it out of `get_all_known_tools()` / the ReAct
    allowlist, so it never shows up as a choice for the normal chat agent —
    it exists purely to be invoked explicitly via the /agent/tool "summary"
    pipeline (see routes.run_selected_tools), to avoid confusing the
    reasoner with two overlapping "explain the scenario results" options.
    """
    return ToolDefinition(
        name="summary_generation",
        description=(
            "Generate a per-constraint breakdown and short summary of one or "
            "more scenarios' evaluation results."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Uses the evaluation data for the given scenario(s) (fetching it if "
            "not already retrieved) to report, for every sustainability "
            "constraint, its index and value, and then drafts a short natural "
            "language summary highlighting what stands out. Internal tool, not "
            "exposed to the general ReAct tool selection — invoke it directly "
            "via the /agent/tool 'summary' pipeline."
        ),
        parameters=[
            ToolParameter(
                name="scenario_ids",
                description=(
                    "IDs of the scenarios to summarize. If omitted, falls back "
                    "to the scenarios already resolved in current_context."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
        ],
        output_description=(
            "Per-scenario constraint index/value breakdown plus a short "
            "natural-language summary."
        ),
        enabled=False,
        tags=["interaction", "read-only", "internal"],
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
    )


def create_new_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_scenario",
        description="Create a new scenario linked to an existing proposal",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Registers a new Scenario for a given Proposal in the platform. "
            "A Scenario is a simulation run exploring a specific parameter configuration. "
            "NOTE: this tool is not yet implemented — it will acknowledge the request "
            "and inform the user that the feature is coming soon."
        ),
        parameters=SCENARIO_PARAMETERS,
        output_description="Acknowledgement that the feature is not yet implemented.",
        tags=["write", "scenario", "not-implemented"],
    )


def edit_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="edit_scenario",
        description="Edit an available scenario",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description="Modify one or more attributes of a scenario that was already defined",
        parameters=SCENARIO_PARAMETERS,
        output_description="Acknowledgement of successful edit or request for more details",
        tags=["write", "scenario"],
    )


def delete_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="delete_scenario",
        description="Delete a scenario",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description="Delete a Scenario in the platform.",
        parameters=[],
        output_description="Acknowledgement of successful deletetion or request for more details",
        tags=["write", "proposal"],
    )


def create_lookup_glossary_tool() -> ToolDefinition:
    return ToolDefinition(
        name="lookup_glossary",
        description=(
            "Look up definitions, aliases, and relationships for domain terms "
            "(e.g. 'problem', 'proposal', 'scenario', 'overtourism', 'digital twin'). "
            "Use this to answer user questions about terminology OR to clarify ambiguous "
            "intent before selecting another tool."
        ),
        category=ToolCategory.UTILITY,
        long_description=(
            "Searches the platform glossary for one or more terms. "
            "Matching is fuzzy: it checks the query against term names, aliases, and "
            "related_terms fields. "
            "Returns definitions, aliases, and related concepts for all matching entries. "
            "Call this whenever: (a) the user asks what a term means, "
            "(b) the user uses unfamiliar vocabulary that might map to a platform concept, "
            "or (c) you need to clarify whether the user is referring to a Problem, "
            "Proposal, or Scenario before proceeding."
        ),
        parameters=[
            ToolParameter(
                name="query",
                description=(
                    "One or more space-separated keywords to look up in the glossary. "
                    "Example: 'scenario simulation' or 'overtourism carrying capacity'."
                ),
                type="string",
                required=True,
            ),
        ],
        output_description=(
            "List of matching glossary entries with their definitions, aliases, "
            "related terms, and examples."
        ),
        tags=["data", "read-only", "glossary", "utility"],
    )


def get_all_agent_tools() -> List[ToolDefinition]:
    return [
        # Utility
        create_lookup_glossary_tool(),
        create_get_system_capabilities_tool(),
        # Data retrieval
        create_list_available_problems_tool(),
        create_list_available_proposals_tool(),
        create_list_available_scenarios_tool(),
        create_get_context_ids_tool(),
        create_get_context_tool(),
        # Interaction
        create_analyze_scenario_results_tool(),
        # Internal-only (enabled=False — see create_summary_generation_tool)
        create_summary_generation_tool(),
        # Creation
        create_new_problem_tool(),
        create_new_proposal_tool(),
        create_new_scenario_tool(),  # (not yet implemented)
        # Editing
        edit_problem_tool(),
        edit_proposal_tool(),
        edit_scenario_tool(),
        # Deletion
        delete_problem_tool(),
        delete_proposal_tool(),
        delete_scenario_tool(),
    ]
