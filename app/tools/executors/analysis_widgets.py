"""Analysis Widgets tool implementation.

Single executor (execute_analysis_widget) backing the show_analysis_widget
tool (see app.tools.definitions.analysis_widgets), replacing the former
execute_comparison_plot / execute_kpi_comparison / execute_show_load_plot /
execute_show_capacity_plot.

The payload data is always the same regardless of widget_type: it's the raw
result of get_evaluation_data for the resolved scenario(s), fetched fresh
for every call rather than read back out of the shared context cache — see
_get_evaluation_payload's docstring for why (in short: plot_data is heavy
and is never persisted into context_cache). Only the resulting widgetName,
and how many scenario_ids are required, differ per widget_type — see
_WIDGET_SPECS.
"""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

from app.agent.nodes.utils import _ensure_data_cached


def _make_widget_result(
    response: str, widget_name: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    action = {
        "type": "SHOW_WIDGET",
        "payload": {"widgetName": widget_name, "data": payload},
    }
    return {"success": True, "response": response, "assistant_action_data": [action]}


# widget_type -> (frontend widgetName, how many scenario_ids it needs).
_WIDGET_SPECS: Dict[str, Dict[str, Any]] = {
    "kpi_comparison": {"widget_name": "indexComparison", "scenario_count": 2},
    "comparison_plot": {"widget_name": "histogramComparison", "scenario_count": 2},
    "load_plot": {"widget_name": "loadPlot", "scenario_count": 1},
    "capacity_plot": {"widget_name": "capacityPlot", "scenario_count": 1},
}

_RESPONSE_TEXT: Dict[str, str] = {
    "kpi_comparison": "Here are the KPI for the two scenarios",
    "comparison_plot": "Ecco il confronto tra gli scenari:",
    "load_plot": "Ecco il grafico del carico turistico:",
    "capacity_plot": "Ecco il grafico di sostenibilità:",
}


def _resolve_scenario_ids(
    state: AgentState, scenario_ids: list | None, count: int
) -> list:
    """Resolve the `count` scenario_ids a widget needs.

    Mirrors the fallback used elsewhere (see execute_summary_generation):
    if the reasoner didn't pass scenario_ids explicitly, fall back to the
    scenarios already resolved in current_context by get_context_ids.
    """
    scenario_ids = scenario_ids or state.cognitive.current_context.get("scenarios", [])
    if not scenario_ids or len(scenario_ids) < count:
        noun = "One scenario_id is" if count == 1 else f"{count} scenario_ids are"
        raise ValueError(
            f"{noun} required for this widget — none (or too few) were "
            "provided and none are resolved in current_context. Call "
            "get_context_ids first to resolve the scenario(s)."
        )
    return scenario_ids[:count]


def _scenario_label(state: AgentState, scenario_id: str) -> str:
    cache = state.cognitive.context_cache
    return cache.get(f"scenarios {scenario_id}", {}).get("name", scenario_id)


def _get_evaluation_payload(state: AgentState, scenario_ids: list) -> Dict[str, Any]:
    """The widget payload data — the raw evaluation dataset (KPIs + raw
    plot_data) for `scenario_ids`, keyed the same way get_evaluation_data
    itself keys its output (e.g. "scenarios <id>").

    Two different data needs are reconciled here:
      - The small KPI/"data" part should stay cached in context_cache for
        the rest of the topic (other tools like analyze_scenario_results /
        generate_summary read it from there) — _ensure_data_cached handles
        that, reusing an earlier fetch this turn (e.g. by
        get_context_details) when possible.
      - plot_data must NOT be written into context_cache. That cache is
        long-lived for the rest of the session/topic, and plot_data is a
        heavy raw per-sample payload — app.utils.common.strip_plot_data is
        applied wherever evaluation_data is written into context_cache
        (see _ensure_data_cached in app/agent/nodes/utils.py and
        execute_get_context_details in app/tools/executors/analysis.py)
        specifically so it never accumulates there. This widget is the one
        place that genuinely needs plot_data — but only transiently, right
        now, to hand to the frontend — so it's fetched fresh here every
        call instead of ever being cached. That means a scenario whose
        KPIs were already warm this turn still costs one extra backend
        call the first time a widget is requested for it; that's an
        accepted, deliberate trade-off for not letting a heavy payload
        accumulate in memory for the rest of the session.
    """
    from app.tools.executor_backend_tools import get_evaluation_data

    _ensure_data_cached(state, {"scenarios": scenario_ids})
    fetched = get_evaluation_data.invoke(
        {"current_context": {"scenarios": scenario_ids}, "tenant": state.tenant}
    )
    return {
        f"scenarios {sid}": fetched.get(f"scenarios {sid}", {}) for sid in scenario_ids
    }


def execute_analysis_widget(
    state: AgentState,
    widget_type: str,
    scenario_ids: list | None = None,
    subsystem: str = "default",
    **kwargs,
) -> Dict[str, Any]:
    """Build the requested analysis widget (kpi_comparison, comparison_plot,
    load_plot, or capacity_plot) using evaluation data already cached (or
    freshly fetched via get_evaluation_data) for the resolved scenario(s).
    """
    logger.info(f"Executing show_analysis_widget tool (widget_type={widget_type!r})")

    spec = _WIDGET_SPECS.get(widget_type)
    if spec is None:
        raise ValueError(
            f"Unknown widget_type {widget_type!r}. Must be one of "
            f"{sorted(_WIDGET_SPECS)}."
        )

    try:
        resolved_ids = _resolve_scenario_ids(
            state, scenario_ids, spec["scenario_count"]
        )
    except ValueError:
        return None

    evaluation_data = _get_evaluation_payload(state, resolved_ids)
    if not any(evaluation_data.values()):
        return None

    payload = {
        "payload": {
            "loading": False,
            "subsystem": subsystem,
            "scenarioIds": resolved_ids,
            "labels": {sid: _scenario_label(state, sid) for sid in resolved_ids},
            "data": evaluation_data,
        }
    }

    return _make_widget_result(
        _RESPONSE_TEXT[widget_type], spec["widget_name"], payload
    )


# widget_type -> fixed, hand-written explanation of how to read that widget.
# Kept alongside _WIDGET_SPECS/_RESPONSE_TEXT above since it's the same
# widget_type vocabulary, but explain_widget itself makes no backend call
# and doesn't touch context_cache/current_context at all.
_WIDGET_EXPLANATIONS: Dict[str, str] = {
    "comparison_plot": (
        "The comparison plot is a bar plot showing the difference in a "
        "system KPI between two scenarios, with one bar per scenario. For "
        "each bar, the confidence interval is also reported, shown in "
        "yellow."
    ),
    "capacity_plot": (
        "In the capacity plot, each line represents a relevant subsystem. "
        "The x and y axes represent the two main sustainability axes. Each "
        "point on the plot is a single simulated day: its color shows "
        "whether that day is sustainable (green), partially sustainable "
        "(yellow), or not sustainable (red), and its opacity shows the "
        "level of uncertainty for that point."
    ),
    "load_plot": (
        "The load plot is shown for a single resource. Each point "
        "represents a simulated day, and points are ordered from low to "
        "high usage of the selected resource. A point's color shows "
        "the probability of a day to exceed the load capacity of that "
        "resource: 0% probability of exceeding (green), 50% probability of "
        "exceeding (yellow), 100% probability exceeding (red)."
    ),
}


def execute_explain_widget(
    state: AgentState, widget_type: str, **kwargs
) -> Dict[str, Any]:
    """Return a fixed, plain-language explanation of how to read the given
    widget type (see _WIDGET_EXPLANATIONS). Purely explanatory: no backend
    call, no dependency on context_cache/current_context, unlike
    execute_analysis_widget above.
    """
    logger.info(f"Executing explain_widget tool (widget_type={widget_type!r})")

    explanation = _WIDGET_EXPLANATIONS.get(widget_type)
    if explanation is None:
        raise ValueError(
            f"Unknown widget_type {widget_type!r} for explain_widget. Must "
            f"be one of {sorted(_WIDGET_EXPLANATIONS)}."
        )

    return {"success": True, "message": explanation}


EXECUTORS = {
    "show_analysis_widget": execute_analysis_widget,
    "explain_widget": execute_explain_widget,
}
