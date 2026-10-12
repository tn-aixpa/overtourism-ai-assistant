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
            "Always run list_available_entities first for the kinds of item involved, "
            "then call this tool to extract relevant IDs."
        ),
        parameters=[
            ToolParameter(
                name="user_intent",
                description="The user's original request or intent, verbatim or lightly paraphrased.",
                type="string",
                required=True,
            ),
            ToolParameter(
                name="entity_types",
                description=(
                    "Which already-fetched lists to search: any of 'problems', "
                    "'proposals', 'scenarios'. Omit to search every list that "
                    "list_available_entities has fetched so far."
                ),
                type="array",
                required=False,
                schema={
                    "items": {
                        "type": "string",
                        "enum": ["problems", "proposals", "scenarios"],
                    }
                },
            ),
        ],
        output_description="Dict with keys 'problems', 'proposals', 'scenarios', each a list of matching IDs.",
        tags=["data", "read-only", "navigation", "resolution"],
        agent_tier="executor",
        allowed_modes=("standalone", "internal"),
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
        requires_territory=True,
        allowed_modes=("standalone", "internal", "system"),
    )


def create_get_configuration_parameters_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_configuration_parameters",
        description=(
            "Look up the tunable simulation parameters that a scenario can override: "
            "what they are, their current value and what values are allowed"
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Describes the configurable parameters of the territory's model, grouped by "
            "category. Every parameter has a 'kind' that decides what a value looks like: "
            "'scalar' (a number), 'categorical' (one choice out of a fixed list, or no "
            "filter) or 'distribution' (a [low, high] range). Each record gives its name "
            "(use THIS as the key in create_new_temp_scenario), label, kind, unit, "
            "'current' value and 'allowed' values (min/max/step for numbers and ranges, "
            "the list of choices for categorical ones). "
            "Ask only for what you need: pass `names` for parameters you can already "
            "identify (name or label), `search` keywords or a `category` for a topic "
            "(e.g. search='parking'). With no arguments you get a compact overview of "
            "every parameter — use that only to answer 'what can I change?'. "
            "Call this before create_new_temp_scenario to identify the parameters the "
            "user means, to learn their kind and current value, and to check what is "
            "allowed; if the user gave no value or size of change, use it to ask them "
            "a precise question."
        ),
        parameters=[
            ToolParameter(
                name="names",
                description=(
                    "Parameters to describe in full, by name or by label. Takes "
                    "precedence over `category` and `search`."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="category",
                description="Only parameters in this category (or categories), e.g. 'Navetta'.",
                type="string",
                required=False,
            ),
            ToolParameter(
                name="search",
                description=(
                    "Keywords matched against names, labels, categories and "
                    "descriptions, best match first (e.g. 'parking price')."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="detail",
                description=(
                    "'summary' (no descriptions) or 'full' (adds descriptions and "
                    "distribution shape). Default: summary without filters, full with."
                ),
                type="string",
                required=False,
                schema={"enum": ["summary", "full"]},
            ),
        ],
        output_description=(
            "total_parameters, categories, matched, parameters_by_category (each record: "
            "name, label, kind, unit, current, allowed, and description when detailed), "
            "plus 'unmatched' for names/categories that were not found."
        ),
        tags=["data", "read-only", "scenario", "parameters"],
        agent_tier="executor",
        requires_territory=True,
        allowed_modes=("standalone", "internal"),
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
        requires_territory=True,
        allowed_modes=("standalone", "internal"),
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
        requires_territory=True,
        allowed_modes=("system",),
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
        requires_territory=True,
        allowed_modes=("system",),
    )


__all__ = [
    "create_get_context_ids_tool",
    "create_get_context_tool",
    "create_analyze_scenario_results_tool",
    "create_get_configuration_parameters_tool",
    "create_summary_generation_tool",
    "create_report_generation_tool",
]
