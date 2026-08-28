# """Analysis Widgets tool implementations."""

# from typing import Any, Dict
# import logging

# from app.agent.state import AgentState

# logger = logging.getLogger(__name__)

# from app.agent.nodes.utils import _ensure_data_cached
# # from app.utils.backend_entities_parsing import _parse_kpis


# def _make_widget_result(
#     response: str, widget_name: str, payload: Dict[str, Any]
# ) -> Dict[str, Any]:
#     action = {
#         "type": "SHOW_WIDGET",
#         "payload": {"widgetName": widget_name, "data": payload},
#     }
#     return {"success": True, "response": response, "assistant_action_data": [action]}


# def _resolve_comparison_scenario_ids(
#     state: AgentState, scenario_ids: list | None
# ) -> list:
#     """Resolve the two scenario_ids to compare.

#     Mirrors the fallback used elsewhere (see execute_summary_generation):
#     if the reasoner didn't pass scenario_ids explicitly, fall back to the
#     scenarios already resolved in current_context by get_context_ids. Also
#     makes sure their evaluation data is actually cached before the caller
#     tries to read sustainability_by_constraint off of it.
#     """
#     scenario_ids = scenario_ids or state.cognitive.current_context.get("scenarios", [])
#     if not scenario_ids or len(scenario_ids) < 2:
#         raise ValueError(
#             "Two scenario_ids are required for a comparison — none (or only "
#             "one) were provided and none are resolved in current_context. "
#             "Call get_context_ids first to resolve the two scenarios to compare."
#         )

#     left_id, right_id = scenario_ids[0], scenario_ids[1]
#     _ensure_data_cached(state, {"scenarios": [left_id, right_id]})
#     return [left_id, right_id]


# def _scenario_label(state: AgentState, scenario_id: str) -> str:
#     cache = state.cognitive.context_cache
#     return cache.get(f"scenarios {scenario_id}", {}).get("name", scenario_id)


# def _resolve_single_scenario_id(
#     state: AgentState, scenario_ids: list | None
# ) -> str | None:
#     """Resolve the one scenario_id a load/capacity plot should be built for.

#     Order of preference: an explicit scenario_ids[0] argument, then
#     whatever get_context_ids already resolved in current_context, then (so
#     plots also work for a just-previewed, not-yet-saved scenario) the
#     pending temp scenario's id.
#     """
#     if scenario_ids:
#         return scenario_ids[0]

#     context_scenarios = state.cognitive.current_context.get("scenarios", [])
#     if context_scenarios:
#         return context_scenarios[0]

#     pending = state.cognitive.pending_temp_scenario
#     if pending:
#         return pending.get("scenario_id")

#     return None


# def _get_plot_data_for_scenario(
#     state: AgentState, scenario_id: str
# ) -> Dict[str, Any] | None:
#     """Fetch (and cache) the raw plot_data for a scenario_id, transparently
#     handling both permanent scenarios and the currently pending temp
#     scenario (see execute_create_new_temp_scenario).

#     Returns None if the scenario can't be resolved to any evaluation data —
#     callers fall back to a mock in that case rather than failing outright.

#     NOTE: plot_data is intentionally never merged into anything returned by
#     get_context_details/get_data_from_context, and is tagged as a heavy
#     field in app/utils/common.py — it's only meant to be consumed here to
#     build a widget payload, never shown to the LLM directly (see
#     clean_scenario in app/tools/backend_tools.py).
#     """
#     from app.tools.executor_backend_tools import get_temp_evaluation_data

#     cache = state.cognitive.context_cache
#     pending = state.cognitive.pending_temp_scenario

#     if pending and pending.get("scenario_id") == scenario_id:
#         cache_key = f"scenarios {scenario_id}"
#         cached = cache.get(cache_key, {})
#         plot_data = cached.get("plot_data") or cached.get("evaluation_data", {}).get(
#             "plot_data"
#         )
#         if plot_data:
#             return plot_data

#         logger.info(f"Fetching temp evaluation data for plot, scenario {scenario_id}")
#         cleaned = get_temp_evaluation_data.invoke(
#             {
#                 "tenant": state.tenant,
#                 "creation_session": pending["creation_session"],
#                 "evaluation_id": pending["evaluation_id"],
#             }
#         )
#         plot_data = cleaned.get("plot_data")
#         # Cache it so a second plot request this turn (e.g. show_load_plot
#         # then show_capacity_plot) doesn't refetch.
#         cache.setdefault(cache_key, {}).update(cleaned)
#         return plot_data

#     # Permanent scenario: warm the shared cache the same way kpi_comparison
#     # does, then read the plot_data that clean_scenario now attaches
#     # alongside the small KPI "data" dict.
#     _ensure_data_cached(state, {"scenarios": [scenario_id]})
#     cached = cache.get(f"scenarios {scenario_id}", {})
#     return cached.get("evaluation_data", {}).get("plot_data")


# def _make_plot_widget_result(
#     response: str,
#     plot_type: str,
#     subsystem: str,
#     plot_payload: Dict[str, Any],
#     chart_summary: list | None,
# ) -> Dict[str, Any]:
#     """Like _make_widget_result, but for the "plot" widget specifically.

#     `plot_type` must be the frontend's own vocabulary — "mono" (load plot)
#     or "bi" (capacity plot) — not the tool names ("load"/"capacity"), since
#     that's what the widget switches its renderer on.

#     The envelope shape matters and must match exactly what the frontend
#     widget expects:
#         data: { payload: { type, subsystem, data }, loading }
#     "loading" is a SIBLING of "payload", not nested inside it — nesting it
#     inside "payload" (as this used to) leaves the widget without a
#     top-level "loading" flag, which is why the constraint curves rendered
#     but the points didn't: whatever reads data.loading to know the plot is
#     ready never found it there.

#     Field order matters too: "response" and "chart_summary" (small, always
#     kept) are set before "assistant_action_data" (which nests the full
#     curves/points arrays). build_prior_results_block's truncation
#     (app/utils/common.py) keeps whole dict keys in insertion order until it
#     runs out of budget, so this ordering makes sure the compact, LLM-useful
#     fields survive intact and the heavy widget payload is what gets
#     dropped/truncated first — keeping this tool's real (potentially large)
#     data out of the reasoner's prompt without needing a special case there.
#     """
#     action = {
#         "type": "SHOW_WIDGET",
#         "payload": {
#             "widgetName": "plot",
#             "data": {
#                 "payload": {
#                     "type": plot_type,
#                     "subsystem": subsystem,
#                     "data": plot_payload,
#                 },
#                 "loading": False,
#             },
#         },
#     }
#     result: Dict[str, Any] = {"success": True, "response": response}
#     if chart_summary is not None:
#         result["chart_summary"] = chart_summary
#     result["assistant_action_data"] = [action]
#     return result


# def execute_comparison_plot(
#     state: AgentState,
#     scenario_ids: list | None = None,
#     **kwargs,
# ) -> Dict[str, Any]:
#     """Build the histogram comparison widget using backend data or safe mocks."""
#     logger.info("Executing comparison_plot tool")

#     try:
#         left_id, right_id = _resolve_comparison_scenario_ids(state, scenario_ids)
#         kpis_main = _parse_kpis(state, left_id)
#         kpis_compare = _parse_kpis(state, right_id)
#     except ValueError:
#         kpis_main = kpis_compare = {}
#         left_id = right_id = None

#     if not kpis_main and not kpis_compare:
#         return None

#     data = {
#         "labelLeft": _scenario_label(state, left_id),
#         "labelRight": _scenario_label(state, right_id),
#         "dataLeft": kpis_main,
#         "dataRight": kpis_compare,
#     }

#     return _make_widget_result(
#         "Ecco il confronto tra gli scenari:",
#         "histogramComparison",
#         {"payload": {"loading": False, **data}},
#     )


# def execute_kpi_comparison(
#     state: AgentState,
#     scenario_ids: list | None = None,
#     **kwargs,
# ) -> Dict[str, Any]:
#     """Build the KPI comparison widget using backend data or safe mocks."""
#     logger.info("Executing kpi_comparison tool")

#     left_id, right_id = _resolve_comparison_scenario_ids(state, scenario_ids)

#     kpis_main = _parse_kpis(state, left_id)
#     kpis_compare = _parse_kpis(state, right_id)
#     if not kpis_main and not kpis_compare:
#         return None

#     comparison = {
#         "kpisMain": kpis_main,
#         "kpisCompare": kpis_compare,
#     }
#     return _make_widget_result(
#         "Here are the KPI for the two scenarios",
#         "indexComparison",
#         comparison,
#     )


# def execute_show_load_plot(
#     state: AgentState,
#     scenario_ids: list | None = None,
#     subsystem: str = "default",
#     payload: Dict[str, Any] | None = None,
#     **kwargs,
# ) -> Dict[str, Any]:
#     """Build the tourist-load plot widget for a single scenario, from real
#     backend evaluation data when available (falling back to a mock only if
#     the scenario/evaluation data can't be resolved)."""
#     logger.info("Executing show_load_plot tool")

#     if payload is not None:
#         plot_payload = payload.get("data", payload)
#         chart_summary = None
#     else:
#         scenario_id = _resolve_single_scenario_id(state, scenario_ids)
#         raw_plot_data = (
#             _get_plot_data_for_scenario(state, scenario_id) if scenario_id else None
#         )

#         if raw_plot_data:
#             from app.utils.backend_entities_parsing import (
#                 build_load_plot_data,
#                 summarize_plot,
#             )

#             plot_payload = build_load_plot_data(raw_plot_data, subsystem)
#             chart_summary = summarize_plot(plot_payload["points"], "load")
#         else:
#             plot_payload = _LOAD_PLOT_MOCK
#             chart_summary = None

#     return _make_plot_widget_result(
#         "Ecco il grafico del carico turistico:",
#         _MONO_PLOT_TYPE,
#         subsystem,
#         plot_payload,
#         chart_summary,
#     )


# def execute_show_capacity_plot(
#     state: AgentState,
#     scenario_ids: list | None = None,
#     subsystem: str = "default",
#     payload: Dict[str, Any] | None = None,
#     **kwargs,
# ) -> Dict[str, Any]:
#     """Build the capacity (sustainability) plot widget for a single
#     scenario, from real backend evaluation data when available (falling
#     back to a mock only if the scenario/evaluation data can't be
#     resolved)."""
#     logger.info("Executing show_capacity_plot tool")

#     if payload is not None:
#         plot_payload = payload.get("data", payload)
#         chart_summary = None
#     else:
#         scenario_id = _resolve_single_scenario_id(state, scenario_ids)
#         raw_plot_data = (
#             _get_plot_data_for_scenario(state, scenario_id) if scenario_id else None
#         )

#         if raw_plot_data:
#             from app.utils.backend_entities_parsing import (
#                 build_capacity_plot_data,
#                 summarize_plot,
#             )

#             plot_payload = build_capacity_plot_data(raw_plot_data, subsystem)
#             chart_summary = summarize_plot(plot_payload["curves"], "capacity")
#         else:
#             plot_payload = _CAPACITY_PLOT_MOCK
#             chart_summary = None

#     return _make_plot_widget_result(
#         "Ecco il grafico di sostenibilità:",
#         _BI_PLOT_TYPE,
#         subsystem,
#         plot_payload,
#         chart_summary,
#     )


# EXECUTORS = {
#     "comparison_plot": execute_comparison_plot,
#     "kpi_comparison": execute_kpi_comparison,
#     "show_load_plot": execute_show_load_plot,
#     "show_capacity_plot": execute_show_capacity_plot,
# }
