"""System Context tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory


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
        agent_tier="executor",
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
            "'evaluation_id' (e.g. a /agent/tool 'summary' entry), folding its scenario_id "
            "into the scenario context like any other scenario."
        ),
        parameters=[],
        output_description="Dictionary with retrieved details for all items in the current context",
        tags=["data", "read-only"],
        agent_tier="executor",
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
        agent_tier="executor",
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
        agent_tier="operative",
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
        agent_tier="operative",
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
        agent_tier="operative",
    )


__all__ = [
    "create_get_context_ids_tool",
    "create_get_context_tool",
    "create_analyze_scenario_results_tool",
    "create_get_configuration_parameters_tool",
    "create_summary_generation_tool",
    "create_report_generation_tool",
]
