"""System Context tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory


def create_get_territorial_index_list_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_territorial_index_list",
        description=(
            "List the concrete territorial indexes available on the platform (e.g. "
            "'Indice di ricettività', 'Indice di turisticità'), with a description and "
            "the years each is available for. Call this whenever the user asks what "
            "indices/indicators exist, or needs to pick one by name before analyzing it."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches the live list of territorial indexes from the backend. Unlike "
            "lookup_glossary (static domain vocabulary), this always reflects the "
            "indexes currently available for the territory, including which ones support "
            "variation analysis and the min/max year each one covers. Call this before "
            "any tool that needs a specific index value/id, whenever the user asks "
            "'what indices are there' or names an index you haven't seen the id for yet."
        ),
        parameters=[],
        output_description=(
            "List of indexes, each with its id (value), display label, description, "
            "whether it supports variation analysis, and its available year range."
        ),
        tags=["data", "read-only", "territorial-index", "navigation"],
        agent_tier="executor",
        allowed_modes=("standalone", "internal"),
    )


def create_show_territorial_index_map_tool() -> ToolDefinition:
    return ToolDefinition(
        name="show_territorial_index_map",
        description=(
            "Show a territorial index's geographic distribution on the map for a given "
            "period. Call this whenever the user wants to see/visualize an index on the "
            "map, or asks which areas are more affected by it (e.g. 'mostrami sulla mappa "
            "l'indice di ricettività per il 2023', 'dove è più alta la turisticità a "
            "giugno 2023?'). The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Fetches the per-area values of a single territorial index for a date range "
            "and builds the 'map' widget (choropleth) from them. "
            "The index_id must be resolved first — if it hasn't been listed yet this "
            "session, call get_territorial_index_list first and use the matching "
            "index's index_id, never a guessed or typed string. "
            "start_date/end_date must always be computed as YYYY-MM-DD, following these "
            "rules: for a full year (e.g. '2023'), start_date is that year's Jan 1st and "
            "end_date is that same year's Dec 1st (the last month expressed as its own "
            "first day, e.g. '2023-12-01' — NOT '2023-12-31'); for a single month (e.g. "
            "'giugno 2023'), start_date and end_date are both that month's 1st (e.g. "
            "'2023-06-01'); for a range spanning several months/years, start_date is the "
            "first day of the first month and end_date is the first day of the last "
            "month. If the user hasn't specified any period, ask them which year/period "
            "they want instead of guessing one. "
            "The SHOW_WIDGET result is appended to assistant_action_data."
        ),
        parameters=[
            ToolParameter(
                name="index_id",
                description=(
                    "The index_id of the territorial index to visualize (e.g. "
                    "'tasso-ricettivita'), resolved via get_territorial_index_list — "
                    "never guess or type this id directly."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="start_date",
                description=(
                    "Start of the period, format YYYY-MM-DD, always the 1st of a month "
                    "(see tool description for how to derive this from a year/month/range "
                    "the user asked about)."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="end_date",
                description=(
                    "End of the period, format YYYY-MM-DD. For full months get the last day"
                    "of the month, while for a full year it's December 31st (see "
                    "tool description for the full conversion rules)."
                ),
                type="string",
                required=True,
            ),
        ],
        output_description="'map' widget (choropleth) to display in the interface, already formatted for assistant_action_data.",
        enabled=True,
        tags=["widget", "map", "territorial-index", "integrated"],
        agent_tier="executor",
        allowed_modes=("standalone",),
    )


def create_show_territorial_index_plot_tool() -> ToolDefinition:
    return ToolDefinition(
        name="show_territorial_index_plot",
        description=(
            "Show a territorial index as a line or bar chart over a given period. "
            "Call this whenever the user wants to see how an index varies over time "
            "(e.g. 'puoi mostrarmi la variazione nel tempo?') or wants to compare "
            "selected areas (e.g. 'puoi mostrarmi la ricettività a Molveno e Trento?'). "
            "For a geographic distribution on the map, use show_territorial_index_map "
            "instead. The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Fetches the variation data of a single territorial index for a date range "
            "and builds a 'lineChart' or 'barChart' widget from it. "
            "The index_id must be resolved first — if it hasn't been listed yet this "
            "session, call get_territorial_index_list first and use the matching "
            "index's index_id, never a guessed or typed string. "
            "start_date/end_date must always be computed as YYYY-MM-DD, following these "
            "rules: for a full year (e.g. '2023'), start_date is that year's Jan 1st and "
            "end_date is that same year's Dec 1st (the last month expressed as its own "
            "first day, e.g. '2023-12-01' — NOT '2023-12-31'); for a single month (e.g. "
            "'giugno 2023'), start_date and end_date are both that month's 1st (e.g. "
            "'2023-06-01'); for a range spanning several months/years, start_date is the "
            "first day of the first month and end_date is the first day of the last "
            "month. If the user hasn't specified any period, ask them which year/period "
            "they want instead of guessing one. "
            "The SHOW_WIDGET result is appended to assistant_action_data."
        ),
        parameters=[
            ToolParameter(
                name="index_id",
                description=(
                    "The index_id of the territorial index to plot (e.g. "
                    "'tasso-ricettivita'), resolved via get_territorial_index_list — "
                    "never guess or type this id directly."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="start_date",
                description=(
                    "Start of the period, format YYYY-MM-DD, always the 1st of a month "
                    "(see tool description for how to derive this from a year/month/range "
                    "the user asked about)."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="end_date",
                description=(
                    "End of the period, format YYYY-MM-DD, always the 1st of a month "
                    "(the last month of the period expressed as its own first day — see "
                    "tool description for the full conversion rules)."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="type",
                description=(
                    "Chart format: 'line' or 'bar'. Use 'line' unless the user asks "
                    "for bars/histogram."
                ),
                type="string",
                required=False,
                default="line",
            ),
            ToolParameter(
                name="granularity",
                description=(
                    "Time interval of the x-axis (e.g. 'monthly'). Omit to use the "
                    "default, 'monthly'."
                ),
                type="string",
                required=False,
                default="monthly",
            ),
            ToolParameter(
                name="spatial_granularity",
                description=(
                    "Territorial level being represented (e.g. 'comune' for "
                    "municipality, or macro area). Omit to use the default, 'comune'."
                ),
                type="string",
                required=False,
                default="comune",
            ),
        ],
        output_description=(
            "'lineChart' or 'barChart' widget to display in the interface, already "
            "formatted for assistant_action_data, plus a small plot_summary of the "
            "parameters used."
        ),
        enabled=True,
        tags=["widget", "plot", "territorial-index", "standalone"],
        agent_tier="executor",
        allowed_modes=("standalone",),
    )


def create_query_territorial_index_values_tool() -> ToolDefinition:
    return ToolDefinition(
        name="query_territorial_index_values",
        description=(
            "Answer factual questions about the NUMERIC values of a territorial index "
            "per municipality, without drawing a map or chart: (a) the value of an index "
            "for one or more named municipalities over a period (e.g. 'qual è il valore "
            "dell'indice di ricettività a Molveno e Trento nel 2023?'), or (b) which "
            "municipalities — or how many — have an index above/below a given value "
            "(e.g. 'quali comuni hanno turisticità superiore a 0.5 a giugno 2023?', "
            "'quanti comuni sono sotto 0.2?'). Also use it when the user asks such a "
            "question about what a map shows. To only SEE the distribution, use "
            "show_territorial_index_map instead."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Reads the same per-municipality data the map widget is built from and does "
            "the filtering/matching/counting in code, so the figures are exact. "
            "The index_id must be resolved first — if it hasn't been listed yet this "
            "session, call get_territorial_index_list first and use the matching "
            "index's index_id, never a guessed or typed string. "
            "start_date/end_date follow the same rules as show_territorial_index_map: "
            "both YYYY-MM-DD, a full year -> Jan 1st to Dec 1st of that year "
            "(e.g. '2023-01-01' to '2023-12-01'), a single month -> both the 1st of "
            "that month, a range -> 1st of the first month to 1st of the last month. "
            "If the user gave no period, ask which one instead of guessing. "
            "Use query_type='values' with 'municipalities' for named municipalities, "
            "and query_type='threshold' with 'threshold' + 'operator' for "
            "above/below questions. Set count_only=true when the user only asks HOW "
            "MANY municipalities match."
        ),
        parameters=[
            ToolParameter(
                name="index_id",
                description=(
                    "The index_id of the territorial index (e.g. 'tasso-ricettivita'), "
                    "resolved via get_territorial_index_list — never guess it."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="start_date",
                description=(
                    "Start of the period, YYYY-MM-DD, always the 1st of a month "
                    "(see tool description)."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="end_date",
                description=(
                    "End of the period, YYYY-MM-DD, always the 1st of the last month "
                    "of the period (see tool description)."
                ),
                type="string",
                required=True,
            ),
            ToolParameter(
                name="query_type",
                description=(
                    "'values' = value of the index for the municipalities listed in "
                    "'municipalities'; 'threshold' = municipalities whose value is "
                    "above/below 'threshold'."
                ),
                type="string",
                required=True,
                schema={"enum": ["values", "threshold"]},
            ),
            ToolParameter(
                name="municipalities",
                description=(
                    "Municipality names exactly as the user wrote them. REQUIRED when "
                    "query_type is 'values'; ignore otherwise."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="threshold",
                description=(
                    "The value to compare against. REQUIRED when query_type is "
                    "'threshold'."
                ),
                type="number",
                required=False,
            ),
            ToolParameter(
                name="operator",
                description=(
                    "Comparison for 'threshold': '>' (higher/above/over), '>=' "
                    "(at least), '<' (lower/below/under), '<=' (at most). Use the "
                    "strict '>' / '<' unless the user says 'at least'/'at most' "
                    "('almeno'/'al massimo')."
                ),
                type="string",
                required=False,
                schema={"enum": [">", ">=", "<", "<="]},
            ),
            ToolParameter(
                name="count_only",
                description=(
                    "For 'threshold': true if the user only wants the NUMBER of "
                    "matching municipalities, not their names. Default false."
                ),
                type="boolean",
                required=False,
                default=False,
            ),
        ],
        output_description=(
            "For 'values': 'values' (area_name + index_value per matched municipality) "
            "and 'not_found' (names that didn't match, with suggestions). For "
            "'threshold': 'matching_count', 'total_areas_considered' and, unless "
            "count_only, 'municipalities' sorted by value (capped; 'list_truncated' "
            "says if so)."
        ),
        tags=["data", "read-only", "territorial-index", "query"],
        agent_tier="executor",
        allowed_modes=("standalone", "internal"),
    )


__all__ = [
    "create_get_territorial_index_list_tool",
    "create_show_territorial_index_map_tool",
    "create_show_territorial_index_plot_tool",
    "create_query_territorial_index_values_tool",
]
