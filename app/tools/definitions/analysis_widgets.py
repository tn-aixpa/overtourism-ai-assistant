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

# Subset of WIDGET_TYPES that explain_widget can describe. kpi_comparison is
# deliberately excluded — it's a plain side-by-side KPI table, not a chart
# with axes/points/colors that benefit from an explanation.
EXPLAINABLE_WIDGET_TYPES = ["comparison_plot", "capacity_plot", "load_plot"]


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
        tags=["widget", "plot", "compare", "kpi", "standalone", "scenario"],
        agent_tier="executor",
        requires_territory=True,
        allowed_modes=("standalone",),
    )


def create_explain_widget_tool() -> ToolDefinition:
    return ToolDefinition(
        name="explain_widget",
        description=(
            "Explain, in plain language, how to read one of the analysis "
            "widgets/plots ('comparison_plot', 'capacity_plot', or "
            "'load_plot') — what its axes, lines, points, and colors mean. "
            "Use this when the user asks what a chart shows, how to "
            "interpret it, or what its colors/axes mean (e.g. 'cosa "
            "rappresenta il grafico di sostenibilità?', 'what do the colors "
            "in the load plot mean?'). This tool does NOT fetch or display "
            "any scenario data — it only explains the widget's visual "
            "encoding. To actually show a widget with real data, use "
            "show_analysis_widget instead (both may be called in the same "
            "turn if the user asks to see AND understand a chart)."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Purely explanatory tool: returns a fixed, hand-written "
            "description of how to read the requested widget type. It makes "
            "no backend call and does not depend on current_context or "
            "context_cache, so it may be called even if no scenario has "
            "been resolved yet. Pick `widget_type` according to which plot "
            "the user is asking about:\n\n"
            "  - 'comparison_plot' (histogramComparison widget): a bar plot "
            "showing the difference in a system KPI between two scenarios, "
            "one bar per scenario. For each bar, the confidence interval is "
            "also reported, shown in yellow.\n\n"
            "  - 'capacity_plot' (capacityPlot widget): each line represents "
            "a relevant subsystem. The x and y axes represent the two main "
            "sustainability axes. Each point is a simulated day; its color "
            "shows whether that day is sustainable (green), partially "
            "sustainable (yellow), or not sustainable (red); its opacity "
            "shows the level of uncertainty.\n\n"
            "  - 'load_plot' (loadPlot widget): shown for a single resource. "
            "Points represent simulated days, ordered from low to high "
            "usage of the selected resource. A point's color shows whether "
            "that day is sustainable (green), partially sustainable "
            "(yellow), or not sustainable (red)."
        ),
        parameters=[
            ToolParameter(
                name="widget_type",
                description=(
                    "Which widget to explain: 'comparison_plot', "
                    "'capacity_plot', or 'load_plot'. See the tool "
                    "description for what each one covers."
                ),
                type="string",
                required=True,
                schema={"enum": EXPLAINABLE_WIDGET_TYPES},
            ),
        ],
        output_description=(
            "A plain-language explanation of the requested widget's axes, "
            "lines/points/bars, and color/opacity encoding."
        ),
        enabled=True,
        tags=["widget", "plot", "explain", "help", "scenario"],
        agent_tier="executor",
        allowed_modes=("standalone", "internal"),
    )


__all__ = [
    "create_analysis_widget_tool",
    "create_explain_widget_tool",
    "WIDGET_TYPES",
    "EXPLAINABLE_WIDGET_TYPES",
]
