"""Analysis Widgets tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory


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
        agent_tier="executor",
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
        agent_tier="executor",
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
        agent_tier="executor",
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
        agent_tier="executor",
    )


__all__ = [
    "create_comparison_plot_tool",
    "create_kpi_comparison_tool",
    "create_show_load_plot_tool",
    "create_show_capacity_plot_tool",
]
