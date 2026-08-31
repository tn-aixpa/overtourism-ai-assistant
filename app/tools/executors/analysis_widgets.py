"""Analysis Widgets tool implementation.

Single executor (execute_analysis_widget) backing the show_analysis_widget
tool (see app.tools.definitions.analysis_widgets), replacing the former
execute_comparison_plot / execute_kpi_comparison / execute_show_load_plot /
execute_show_capacity_plot.

The payload data is always the same regardless of widget_type: it's the raw
result of get_evaluation_data for the resolved scenario(s) (read through the
shared context cache via _ensure_data_cached, so a scenario already fetched
earlier this turn — e.g. by get_context_details — isn't refetched). Only the
resulting widgetName, and how many scenario_ids are required, differ per
widget_type — see _WIDGET_SPECS.
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
    """The widget payload data — always the raw result of get_evaluation_data
    for `scenario_ids`, keyed the same way get_evaluation_data itself keys
    its output (e.g. "scenarios <id>"). Ensures the data is cached (fetching
    only what's missing) rather than refetching every time."""
    _ensure_data_cached(state, {"scenarios": scenario_ids})
    cache = state.cognitive.context_cache
    return {
        f"scenarios {sid}": cache.get(f"scenarios {sid}", {}).get("evaluation_data", {})
        for sid in scenario_ids
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
        resolved_ids = _resolve_scenario_ids(state, scenario_ids, spec["scenario_count"])
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


EXECUTORS = {
    "show_analysis_widget": execute_analysis_widget,
}
