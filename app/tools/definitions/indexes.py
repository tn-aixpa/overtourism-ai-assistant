"""System Context tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory


def create_get_territorial_index_list_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_territorial_index_list",
        description=(
            "List the concrete territorial indexes available on the platform (e.g. "
            "'Indice di ricettività', 'Indice di turisticità'), with a description and "
            "the years each is available for. Also lists additional indicators that "
            "can be combined with any concrete index. Call this whenever the user asks what "
            "indices/indicators exist, or needs to pick one by name before analyzing it."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetches the live list of territorial indexes from the backend. Unlike "
            "lookup_glossary (static domain vocabulary), this always reflects the "
            "indexes currently available for the territory, including which ones support "
            "variation analysis and the min/max year each one covers. It also returns "
            "additional_labels (such as tasso-variazione and incidenza-periodo); these "
            "are not standalone indexes, but can be combined with any indicator. Call this before "
            "any tool that needs a specific index value/id, whenever the user asks "
            "'what indices are there' or names an index you haven't seen the id for yet."
        ),
        parameters=[],
        output_description=(
            "A dictionary with 'indexes' (each with id, label, description, unit, "
            "variation support and year range) and 'additional_labels' (additional "
            "index operations and descriptions that can be combined with an index)."
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
            "The additional_labels returned by that list are combination operations: "
            "for 'tasso-variazione', set index_id to that label's id, indicator to the "
            "chosen concrete index id, and provide both comparison dates; for "
            "'incidenza-periodo', set index_id to that label's id, indicator to the "
            "chosen concrete index id, and provide seasonality. "
            "spatial_granularity selects the territorial level: 'comune' (default), "
            "'macro_area' (also referred to as APT, Azienda per il Turismo), or "
            "'provincia'. If the user asks for an APT, use 'macro_area'. "
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
            ToolParameter(
                name="spatial_granularity",
                description=(
                    "Territorial level represented on the map: 'comune' (municipality) "
                    "'macro_area' (also called APT, Azienda per il Turismo), or "
                    "'provincia'. Use 'macro_area' when the user asks for an APT. "
                    "Defaults to 'comune'."
                ),
                type="string",
                required=False,
                default="comune",
                schema={"enum": ["comune", "macro_area", "provincia"]},
            ),
            ToolParameter(
                name="indicator",
                description=(
                    "Concrete index id to analyze when index_id is an additional label "
                    "('tasso-variazione' or 'incidenza-periodo'). Resolve it from "
                    "get_territorial_index_list. Required for those two labels; omit "
                    "for an ordinary index."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="start_date_comparison",
                description=(
                    "Comparison-period start date (YYYY-MM-DD), required when "
                    "index_id='tasso-variazione'; omit otherwise."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="end_date_comparison",
                description=(
                    "Comparison-period end date (YYYY-MM-DD), required when "
                    "index_id='tasso-variazione'; omit otherwise."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="seasonality",
                description=(
                    "Required when index_id='incidenza-periodo': 'weekend', "
                    "'weekdays' (working days), 'festivities', 'summer-months', or "
                    "'winter-months'. Omit otherwise."
                ),
                type="string",
                required=False,
                schema={
                    "enum": [
                        "weekend",
                        "weekdays",
                        "festivities",
                        "summer-months",
                        "winter-months",
                    ]
                },
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
            "Available temporal granularities are 'yearly', 'monthly', 'weekly' and "
            "'daily'. The spatial_granularity selects the territorial level: 'comune' "
            "(default), 'macro_area' (also referred to as APT, Azienda per il Turismo), "
            "or 'provincia'. If the user asks for an APT, use 'macro_area'. "
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
                    "Time interval of the x-axis: 'yearly', 'monthly', 'weekly' or "
                    "'daily'. Omit to use the default, 'monthly'."
                ),
                type="string",
                required=False,
                default="monthly",
                schema={"enum": ["yearly", "monthly", "weekly", "daily"]},
            ),
            ToolParameter(
                name="spatial_granularity",
                description=(
                    "Territorial level being represented: 'comune' (municipality) or "
                    "'macro_area' (also called APT, Azienda per il Turismo), or "
                    "'provincia'. Use 'macro_area' for an APT. Omit to use the "
                    "default, 'comune'."
                ),
                type="string",
                required=False,
                default="comune",
                schema={"enum": ["comune", "macro_area", "provincia"]},
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
            "'quanti comuni sono sotto 0.2?'), or the N municipalities with the "
            "highest/lowest values for an index in a period. Also use it when the user asks such a "
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
            "Additional labels can be combined with a concrete index: for "
            "'tasso-variazione', use that label as index_id and provide indicator plus "
            "both comparison dates; for 'incidenza-periodo', use that label as index_id "
            "and provide indicator plus seasonality. These parameters are required "
            "only for their corresponding additional label. "
            "start_date/end_date must be YYYY-MM-DD: a full calendar year -> Jan 1st "
            "to Dec 31st of that year (e.g. '2023-01-01' to '2023-12-31'), a single month -> both the 1st of "
            "that month, a range -> 1st of the first month to 1st of the last month. "
            "If the user gave no period, ask which one instead of guessing. "
            "Use query_type='values' with 'municipalities' for named municipalities, "
            "and query_type='threshold' with 'threshold' + 'operator' for "
            "above/below questions. For highest/lowest rankings, use "
            "query_type='ranking', ranking_order='highest' or 'lowest', and top_n "
            "equal to the number requested; if the user gives no number, omit top_n "
            "to use the default of 5. If more than N municipalities tie for the "
            "highest/lowest value, report the tie count and list all tied municipalities "
            "when the tie count is at most 20; otherwise report the count without names. "
            "Set count_only=true when the user only "
            "asks HOW MANY municipalities match."
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
                    "'values' = values for listed municipalities; 'threshold' = "
                    "municipalities above/below a threshold; 'ranking' = the N "
                    "municipalities with the highest or lowest values."
                ),
                type="string",
                required=True,
                schema={"enum": ["values", "threshold", "ranking"]},
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
            ToolParameter(
                name="ranking_order",
                description=(
                    "Required for query_type='ranking': 'highest' for largest values "
                    "first or 'lowest' for smallest values first."
                ),
                type="string",
                required=False,
                schema={"enum": ["highest", "lowest"]},
            ),
            ToolParameter(
                name="top_n",
                description=(
                    "For query_type='ranking': number of municipalities requested "
                    "(1–20). Use the exact N requested; defaults to 5 when omitted. "
                    "If more than N municipalities tie at the highest/lowest value, "
                    "the result includes all tied municipalities if there are at most "
                    "20; larger ties return the count without names."
                ),
                type="integer",
                required=False,
                default=5,
            ),
            ToolParameter(
                name="indicator",
                description=(
                    "Concrete index id to analyze when index_id is an additional label "
                    "('tasso-variazione' or 'incidenza-periodo'). Resolve it from "
                    "get_territorial_index_list. Required for those labels; omit for "
                    "an ordinary index."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="start_date_comparison",
                description=(
                    "Comparison-period start date (YYYY-MM-DD), required when "
                    "index_id='tasso-variazione'; omit otherwise."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="end_date_comparison",
                description=(
                    "Comparison-period end date (YYYY-MM-DD), required when "
                    "index_id='tasso-variazione'; omit otherwise."
                ),
                type="string",
                required=False,
            ),
            ToolParameter(
                name="seasonality",
                description=(
                    "Required when index_id='incidenza-periodo': 'weekend', "
                    "'weekdays' (working days), 'festivities', 'summer-months', or "
                    "'winter-months'. Omit otherwise."
                ),
                type="string",
                required=False,
                schema={
                    "enum": [
                        "weekend",
                        "weekdays",
                        "festivities",
                        "summer-months",
                        "winter-months",
                    ]
                },
            ),
        ],
        output_description=(
            "For 'values': 'values' (area_name + index_value per matched municipality) "
            "and 'not_found' (names that didn't match, with suggestions). For "
            "'threshold': 'matching_count', 'total_areas_considered' and, unless "
            "count_only, 'municipalities' sorted by value (capped; 'list_truncated' "
            "says if so). For 'ranking': 'ranked_municipalities' in requested order, "
            "each with area_name and index_value, plus returned_count and the total "
            "number of areas considered. Rankings use unrounded backend values for "
            "ordering, and return the displayed index values as received. If a tie "
            "for the extreme value exceeds the requested N, the tie count is reported; "
            "the full tied list is returned only when its size is at most 20, otherwise "
            "'ranking_list_omitted' is true and no names are returned."
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
