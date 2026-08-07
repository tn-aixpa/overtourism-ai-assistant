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
    TEMP_SCENARIO_PARAMETERS,
)

logger = logging.getLogger(__name__)

WIDGET_TOOL_NAMES = {
    "comparison_plot",
    "kpi_comparison",
    "show_capacity_plot",
    "show_load_plot",
}


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
            "including descriptions, metadata, relationships, and other textual attributes. "
            "Also resolves a temporary (not-yet-saved) scenario/evaluation when "
            "current_context carries a 'temp' entry with 'creation_session' and "
            "'evaluation_id' (e.g. the /agent/tool 'summary-temp' pipeline), folding "
            "its scenario_id into the scenario context like any other scenario."
        ),
        parameters=[],
        output_description="Dictionary with retrieved details for all items in the current context",
        tags=["data", "read-only"],
    )


def create_get_data_from_link_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_data_from_link",
        description=(
            "Fetch data from a URL, following links found in problem or proposal fields, "
            "and return the content or an error summary if the link cannot be retrieved."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetch the content at the provided URL. If the URL points to a web page, return a text snippet and extracted title where available. "
            "If the link is broken, blocked, or otherwise unavailable, return a clear error message."
        ),
        parameters=[
            ToolParameter(
                name="url",
                description="The link to fetch data from.",
                type="string",
                required=True,
            ),
        ],
        output_description="URL fetch result with content summary or error details",
        tags=["data", "read-only", "link", "web"],
    )


def create_get_base_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_base_scenario",
        description="Retrieve the base scenario ID from the backend.",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetch the ID of the base scenario from the backend, using the same backend tool as the platform's get_base_scenario helper."
        ),
        parameters=[],
        output_description="The base scenario ID",
        tags=["data", "read-only", "scenario", "base"],
    )


def create_get_configuration_parameters_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_configuration_parameters",
        description=(
            "Retrieve all tunable simulation parameters (widgets) that scenarios can override"
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches every configurable index/parameter from the backend (parking, beach, "
            "hotel, restaurant, and flow parameters), grouped by category, with its "
            "index_id, current value, allowed range/step, and description. "
            "Call this before create_new_temp_scenario whenever you need to: resolve a "
            "parameter the user referred to by name (e.g. 'parking turnover'); read its "
            "current value in order to compute a relative change (e.g. 'double X', "
            "'increase Y by 20%'); or check the min/max/step bounds of a value the user "
            "wants to set."
        ),
        parameters=[],
        output_description=(
            "Widgets grouped by category, each with index_id, index_name, description, "
            "current value, min, max, and step."
        ),
        tags=["data", "read-only", "scenario", "parameters"],
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


def create_comparison_plot_tool() -> ToolDefinition:
    return ToolDefinition(
        name="comparison_plot",
        description=(
            "Show the sustainability index histogram comparing two scenarios. "
            "MUST always be called when the user asks for a comparison between two scenarios, "
            "TOGETHER with analyze_scenario_results (not instead of it). "
            "The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Builds the histogramComparison widget using evaluation data already cached "
            "for the two scenarios in the current context, or mock values if data is unavailable. "
            "INVOCATION RULE: this call must be included in the same turn as "
            "analyze_scenario_results for a scenario comparison — it is not an alternative to it. "
            "Do NOT call this tool for single scenarios or for requests that do not explicitly "
            "involve a comparison between two scenarios. "
            "The SHOW_WIDGET result is appended to assistant_action_data."
        ),
        parameters=[
            ToolParameter(
                name="scenario_ids",
                description=(
                    "IDs of the two scenarios to compare. If omitted, the tool "
                    "uses the scenarios already resolved in current_context."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
        ],
        output_description="histogramComparison widget to display in the interface, already formatted for assistant_action_data.",
        enabled=False,
        tags=["widget", "compare", "integrated", "scenario"],
    )


def create_kpi_comparison_tool() -> ToolDefinition:
    return ToolDefinition(
        name="kpi_comparison",
        description=(
            "Show the visual KPI comparison view between two scenarios. "
            "Call ONLY if the user EXPLICITLY asks for a visual representation of the KPIs "
            "of two scenarios (e.g. 'show me the KPIs side by side', 'compare the KPIs of the two scenarios'). "
            "The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Builds the index comparison widget with the KPIs of two scenarios. "
            "INVOCATION RULE: use only when the user explicitly requests a visual representation "
            "of the KPIs of two scenarios — NOT for a generic scenario comparison "
            "(use comparison_plot for that). "
            "May be called alone or together with analyze_scenario_results. "
            "Do NOT call this tool for single scenarios or for generic comparison requests. "
            "The SHOW_WIDGET result is appended to assistant_action_data."
        ),
        parameters=[
            ToolParameter(
                name="scenario_ids",
                description=(
                    "IDs of the two scenarios to compare. If omitted, the tool "
                    "uses the scenarios already resolved in current_context."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            )
        ],
        output_description="indexComparison widget to display in the interface, already formatted for assistant_action_data.",
        enabled=False,
        tags=["widget", "kpi", "compare", "integrated"],
    )


def create_show_load_plot_tool() -> ToolDefinition:
    return ToolDefinition(
        name="show_load_plot",
        description=(
            "Show the load plot for a single scenario. "
            "Call ONLY if the user EXPLICITLY asks for the load graph/plot of a single scenario "
            "(e.g. 'show me the load plot', 'display the tourist load chart'). "
            "The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Generates the load plot widget for a single scenario. "
            "INVOCATION RULE: use only when the user explicitly requests the load "
            "graph of a single scenario. Do NOT call for scenario comparisons "
            "(use comparison_plot for those) and do NOT call for generic scenario evaluation "
            "(use show_capacity_plot for that). "
            "May be called alone or together with analyze_scenario_results. "
            "The SHOW_WIDGET result is appended to assistant_action_data."
        ),
        parameters=[
            ToolParameter(
                name="scenario_ids",
                description=(
                    "List containing the ID of the scenarios to analyze. If omitted, the "
                    "tool uses the scenario already resolved in current_context (or, "
                    "failing that, the most recently previewed temporary scenario)."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="subsystem",
                description=(
                    "Which constraint/subsystem to plot the load for (e.g. 'parcheggi', "
                    "'spiaggia', 'alberghi', 'ristoranti'). Defaults to 'default', which "
                    "plots the overall destination load across all constraints."
                ),
                type="string",
                required=False,
            ),
        ],
        output_description="Turistic load plot widget to display in the interface, already formatted for assistant_action_data.",
        enabled=False,
        tags=["widget", "plot", "turistic load", "integrated"],
    )


def create_show_capacity_plot_tool() -> ToolDefinition:
    return ToolDefinition(
        name="show_capacity_plot",
        description=(
            "Show the capacity plot (sustainability chart) for a scenario evaluation. "
            "MUST always be called when the user asks for an evaluation of a scenario, "
            "TOGETHER with analyze_scenario_results. "
            "The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Generates the capacity plot widget (limit curve and scenario points). "
            "INVOCATION RULE: must be called in every turn where analyze_scenario_results is called "
            "for a scenario evaluation — it is not an alternative to it. "
            "Do NOT call for comparisons between two scenarios (use comparison_plot for those) and "
            "do NOT call when the user explicitly asks for the load graph "
            "(use show_load_plot for that). "
            "The SHOW_WIDGET result is appended to assistant_action_data."
        ),
        parameters=[
            ToolParameter(
                name="scenario_ids",
                description=(
                    "List containing the ID of the scenarios to analyze. If omitted, the "
                    "tool uses the scenario already resolved in current_context (or, "
                    "failing that, the most recently previewed temporary scenario)."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="subsystem",
                description=(
                    "Which constraint/subsystem to plot capacity for (e.g. 'parcheggi', "
                    "'spiaggia', 'alberghi', 'ristoranti'). Defaults to 'default', which "
                    "plots every constraint curve together."
                ),
                type="string",
                required=False,
            ),
        ],
        output_description="Sustainability plot widget to display in the interface, already formatted for assistant_action_data.",
        enabled=False,
        tags=["widget", "plot", "sustainability", "integrated"],
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


def create_report_generation_tool() -> ToolDefinition:
    """Internal-only tool that renders a full PDF report (chapters for the
    given problems/proposals/scenarios, plus a conclusion when appropriate).

    `enabled=False` for the same reason as create_summary_generation_tool:
    it's only meant to be invoked explicitly via the /agent/tool
    'pdf-report' pipeline (see routes.run_selected_tools), not chosen by
    the ReAct reasoner.
    """
    return ToolDefinition(
        name="report_generation",
        description=(
            "Generate a full PDF report covering one or more problems, "
            "proposals and/or scenarios."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Uses the data already retrieved for the given problem(s), "
            "proposal(s) and/or scenario(s) (fetching it if not already "
            "cached) to write a structured report — an introduction, one "
            "chapter per problem, one per proposal, a chapter with each "
            "scenario's description and evaluation results, and (unless "
            "the report is just a single standalone scenario) a "
            "Conclusion chapter summarizing the document — and renders it "
            "to a PDF file on disk. Internal tool, not exposed to the "
            "general ReAct tool selection — invoke it directly via the "
            "/agent/tool 'pdf-report' pipeline."
        ),
        parameters=[
            ToolParameter(
                name="current_context",
                description=(
                    "problems/proposals/scenarios ids to include in the report. "
                    "If omitted, falls back to the ids already resolved in "
                    "current_context."
                ),
                type="object",
                required=False,
            ),
        ],
        output_description=(
            "Confirmation that the report was generated, plus the path to "
            "the rendered PDF file."
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


def create_new_temp_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_temp_scenario",
        description=(
            "Create a temporary, unsaved scenario with modified parameter values and evaluate it"
        ),
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Applies the given parameter overrides on top of a base scenario, creates a "
            "throwaway (temporary) scenario from them, and immediately evaluates it. Use this "
            "to preview the effect of a what-if change (e.g. 'what if I double the parking "
            "turnover?') before deciding whether to save it as a real scenario. If the user "
            "expresses the change in relative terms ('double', 'increase by 20%', ...), first "
            "call get_configuration_parameters to resolve the parameter's current value and "
            "compute the final numeric value yourself, then pass the resulting index_id -> "
            "value mapping here. This tool does not require user confirmation and does not "
            "persist anything permanently — nothing is saved until create_new_scenario is "
            "called afterwards on the scenario it produced."
        ),
        parameters=TEMP_SCENARIO_PARAMETERS,
        output_description=(
            "The temporary scenario_id, its evaluation_id, and the evaluation results "
            "(sustainability index and per-constraint breakdown)."
        ),
        tags=["scenario", "simulation", "preview"],
    )


def create_new_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_scenario",
        description="Save a previously previewed temporary scenario as a permanent scenario",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Persists the temporary scenario that create_new_temp_scenario already created "
            "and evaluated, giving it a permanent name and description. "
            "create_new_temp_scenario MUST have been called earlier in the conversation — a "
            "scenario and its evaluation must already exist before it can be saved. If no "
            "temporary scenario is available yet, ask the user what values they want to "
            "simulate and call create_new_temp_scenario first, let them review the results, "
            "and only call this tool once they confirm they want to keep it."
        ),
        parameters=SCENARIO_PARAMETERS,
        output_description="Acknowledgement of successful save with the final scenario_id.",
        tags=["write", "scenario"],
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
        create_get_data_from_link_tool(),
        create_get_base_scenario_tool(),
        create_get_configuration_parameters_tool(),
        # Interaction
        create_analyze_scenario_results_tool(),
        create_comparison_plot_tool(),
        create_kpi_comparison_tool(),
        create_show_capacity_plot_tool(),
        create_show_load_plot_tool(),
        # Internal-only (enabled=False — see create_summary_generation_tool)
        create_summary_generation_tool(),
        create_report_generation_tool(),
        # Creation
        create_new_problem_tool(),
        create_new_proposal_tool(),
        create_new_temp_scenario_tool(),
        create_new_scenario_tool(),
        # Editing
        edit_problem_tool(),
        edit_proposal_tool(),
        edit_scenario_tool(),
        # Deletion
        delete_problem_tool(),
        delete_proposal_tool(),
        delete_scenario_tool(),
    ]
