"""Analysis Widgets tool definitions.

This used to be four separate tools (comparison_plot, kpi_comparison,
show_load_plot, show_capacity_plot). They're now a single tool
(show_analysis_widget) that takes a `widget_type` parameter, so the
reasoner picks ONE tool and tells it which widget to build instead of
picking between four similarly-shaped tools. See
app.tools.executors.analysis_widgets for the implementation — the payload
data is always the same (the raw result of get_evaluation_data for the
resolved scenario(s)); only the resulting widgetName differs per
widget_type.
"""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory

WIDGET_TYPES = ["kpi_comparison", "comparison_plot", "load_plot", "capacity_plot"]


def create_analysis_widget_tool() -> ToolDefinition:
    return ToolDefinition(
        name="show_analysis_widget",
        description=(
            "Show an analysis widget (KPI comparison, comparison plot, load "
            "plot, or capacity plot) for one or two scenarios. Pick "
            "`widget_type` according to the request:\n"
            "  - 'kpi_comparison': ONLY on an explicit, specific request to "
            "visually compare the KPIs of two scenarios (e.g. 'show me the "
            "KPIs side by side').\n"
            "  - 'comparison_plot': on a request for a visual comparison, and "
            "it MUST ALWAYS be called (together with analyze_scenario_results) "
            "whenever two scenarios are being compared.\n"
            "  - 'load_plot': on a general request for a graphical result of a "
            "single scenario, and it MUST ALWAYS be called (together with "
            "analyze_scenario_results) whenever data is retrieved/evaluated "
            "for a single scenario.\n"
            "  - 'capacity_plot': ONLY on an explicit, specific request for "
            "the capacity/sustainability plot.\n"
            "The result is automatically appended to assistant_action_data."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Single entry point for all four analysis widgets, replacing the "
            "former separate comparison_plot / kpi_comparison / "
            "show_load_plot / show_capacity_plot tools. The widget's payload "
            "data is always the same regardless of widget_type — the raw "
            "result of get_evaluation_data for the resolved scenario(s), read "
            "from the shared context cache — only the resulting widgetName "
            "(and how many scenario_ids are required) differs per "
            "widget_type:\n\n"
            "  - widget_type='comparison_plot' -> histogramComparison widget. "
            "INVOCATION RULE: must be included in the same turn as "
            "analyze_scenario_results whenever the user is comparing two "
            "scenarios — it is not an alternative to it. Requires two "
            "scenario_ids.\n\n"
            "  - widget_type='kpi_comparison' -> indexComparison widget. Use "
            "ONLY when the user explicitly asks to see the KPIs of two "
            "scenarios side by side (e.g. 'show me the KPIs side by side', "
            "'compare the KPIs of the two scenarios'). Requires two "
            "scenario_ids. Never a substitute for comparison_plot.\n\n"
            "  - widget_type='load_plot' -> loadPlot widget. Use for a "
            "general request to see a single scenario's result graphically, "
            "and ALWAYS call it (together with analyze_scenario_results) "
            "whenever scenario data is being retrieved/evaluated for one "
            "scenario. Requires one scenario_id.\n\n"
            "  - widget_type='capacity_plot' -> capacityPlot widget. Use "
            "ONLY on an explicit, specific request for the "
            "capacity/sustainability plot (e.g. 'mostrami il grafico di "
            "sostenibilità'). Requires one scenario_id.\n\n"
            "If scenario_ids is omitted, the tool uses the scenario(s) "
            "already resolved in current_context. The SHOW_WIDGET result is "
            "appended to assistant_action_data, with widgetName set "
            "according to widget_type."
        ),
        parameters=[
            ToolParameter(
                name="widget_type",
                description=(
                    "Which widget to build: 'kpi_comparison', "
                    "'comparison_plot', 'load_plot', or 'capacity_plot'. See "
                    "the tool description for the selection rule for each."
                ),
                type="string",
                required=True,
                schema={"enum": WIDGET_TYPES},
            ),
            ToolParameter(
                name="scenario_ids",
                description=(
                    "IDs of the scenario(s) the widget is about. "
                    "'comparison_plot' and 'kpi_comparison' need two; "
                    "'load_plot' and 'capacity_plot' need one. If omitted, "
                    "the tool uses the scenario(s) already resolved in "
                    "current_context."
                ),
                type="array",
                required=False,
                schema={"items": {"type": "string"}},
            ),
            ToolParameter(
                name="subsystem",
                description=(
                    "Only used by 'load_plot' and 'capacity_plot'. Which "
                    "constraint/subsystem to plot (e.g. 'parcheggi', "
                    "'spiaggia', 'alberghi', 'ristoranti'). Defaults to "
                    "'default', which plots the overall/every-constraint "
                    "result."
                ),
                type="string",
                required=False,
            ),
        ],
        output_description=(
            "One of the analysis widgets (indexComparison, "
            "histogramComparison, loadPlot, capacityPlot) to display in the "
            "interface, already formatted for assistant_action_data."
        ),
        enabled=True,
        tags=["widget", "plot", "compare", "kpi", "integrated", "scenario"],
        agent_tier="executor",
    )


__all__ = ["create_analysis_widget_tool", "WIDGET_TYPES"]
