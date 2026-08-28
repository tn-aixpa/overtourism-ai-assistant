# import logging
# from typing import Any, Dict, List, Optional

# from app.agent.state import AgentState

# logger = logging.getLogger(__name__)


# # Mirrors PlotService.getDashForGroup
# _GROUP_DASH = {
#     "parcheggi": "solid",
#     "spiaggia": "dot",
#     "alberghi": "dash",
#     "ristoranti": "dashdot",
# }


# def _dash_for_group(group_name: str) -> str:
#     return _GROUP_DASH.get(group_name, "solid")


# def _get_subsystem_series(
#     plot_data: Dict[str, Any], subsystem: str
# ) -> tuple[List[float], List[float]]:
#     """Return (index_values, usage_values) for the given subsystem.

#     "default" uses the global (all-constraints) arrays; any other value is
#     looked up in the *_by_constraint dicts, mirroring
#     PlotService._getUncertaintyData / the sottosistemaSelezionato === 'default'
#     branches throughout plot.service.ts.
#     """
#     if subsystem == "default":
#         return (
#             list(plot_data.get("uncertainty") or []),
#             list(plot_data.get("usage") or []),
#         )

#     uncertainty_by_constraint = plot_data.get("uncertainty_by_constraint") or {}
#     usage_by_constraint = plot_data.get("usage_by_constraint") or {}
#     return (
#         list(uncertainty_by_constraint.get(subsystem) or []),
#         list(usage_by_constraint.get(subsystem) or []),
#     )


# def _build_uncertainty_records(
#     plot_data: Dict[str, Any], subsystem: str
# ) -> List[Dict[str, float]]:
#     """Zip the per-sample arrays into the {tourists, excursionists, index,
#     usage, usage_uncertainty} records the frontend keeps under
#     kpis.uncertainty / kpis.uncertainty_by_constraint[subsystem].

#     index and usage_uncertainty are the same underlying per-sample
#     sustainability index (0..1, higher = safer) — this mirrors the mocked
#     payload in the original tool_executor.py, where both fields always
#     carried the same value.
#     """
#     sample_x = plot_data.get("sample_x") or []
#     sample_y = plot_data.get("sample_y") or []
#     index_values, usage_values = _get_subsystem_series(plot_data, subsystem)

#     n = min(len(sample_x), len(sample_y), len(index_values), len(usage_values))
#     records = []
#     for i in range(n):
#         index = index_values[i]
#         records.append(
#             {
#                 "tourists": sample_x[i],
#                 "excursionists": sample_y[i],
#                 "index": index,
#                 "usage": usage_values[i],
#                 "usage_uncertainty": index,
#             }
#         )
#     return records


# def build_load_plot_data(
#     plot_data: Dict[str, Any], subsystem: str = "default"
# ) -> Dict[str, Any]:
#     """Port of PlotService.renderMonoDimensionale: an ordered-by-usage
#     scatter of every sample, colored by risk, plus the capacity threshold.
#     """
#     records = _build_uncertainty_records(plot_data, subsystem)

#     if not records:
#         return {
#             "curves": [],
#             "points": [],
#             "kpis": {"uncertainty": []},
#             "capacity_mean": None,
#             "xMax": 0,
#             "yMax": 0,
#         }

#     sorted_records = sorted(records, key=lambda r: r["usage"])
#     x = list(range(len(sorted_records)))
#     y = [r["usage"] for r in sorted_records]
#     color_values = [r["usage_uncertainty"] for r in sorted_records]
#     risk = [100 * v for v in color_values]

#     usage_max = max(y) if y else 0
#     y_axis_max = usage_max * 1.2

#     capacity_mean = (
#         plot_data.get("capacity_mean")
#         if subsystem == "default"
#         else (plot_data.get("capacity_mean_by_constraint") or {}).get(subsystem)
#     )

#     points = [
#         {
#             "name": "Presenze",
#             "x": x,
#             "y": y,
#             "customdata": risk,
#             "marker": {"color": color_values, "size": 8},
#             "mode": "markers",
#             "type": "scatter",
#         }
#     ]

#     return {
#         "curves": [],
#         "points": points,
#         "kpis": {"uncertainty": records},
#         "capacity_mean": capacity_mean,
#         "xMax": len(x),
#         "yMax": y_axis_max,
#     }


# def _risk_color(avg_index: float) -> str:
#     """Map an average sustainability index (0..1, higher = safer) to a
#     single representative color, since the "bi" plot widget's Point
#     contract (see plot.service.ts renderFunctionPlot / the frontend's
#     `marker: pt.marker ?? { color: pt.color ?? 'black', size: 8 }`) takes
#     one color per point series, not a per-point array/colorscale — that
#     richer gradient coloring is only used by the standalone Angular
#     dashboard's own direct Plotly rendering, not this widget."""
#     if avg_index >= 0.7:
#         return "rgb(46,160,67)"  # green — safe
#     if avg_index >= 0.4:
#         return "rgb(240,166,35)"  # amber — borderline
#     return "rgb(218,54,51)"  # red — overloaded


# def build_capacity_plot_data(
#     plot_data: Dict[str, Any], subsystem: str = "default"
# ) -> Dict[str, Any]:
#     """Port of PlotService.preparePlotInput + renderFunctionPlot /
#     renderBidimensionale: the constraint curves plus a scatter of every
#     sample on the tourists/excursionists plane.
#     """
#     constraint_curves = plot_data.get("constraint_curves") or {}

#     curves = []
#     for group_name, curve_xy in constraint_curves.items():
#         if subsystem != "default" and group_name != subsystem:
#             continue
#         if not curve_xy or len(curve_xy) < 2:
#             continue
#         curves.append(
#             {
#                 "name": group_name,
#                 "x": curve_xy[0],
#                 "y": curve_xy[1],
#                 "color": "black",
#                 "dash": _dash_for_group(group_name),
#             }
#         )

#     records = _build_uncertainty_records(plot_data, subsystem)
#     points: List[Dict[str, Any]] = []
#     if records:
#         avg_index = sum(r["index"] for r in records) / len(records)
#         color = _risk_color(avg_index)
#         points.append(
#             {
#                 "name": "Presenze",
#                 "x": [r["tourists"] for r in records],
#                 "y": [r["excursionists"] for r in records],
#                 "color": color,
#                 "marker": {"size": 6, "color": color},
#             }
#         )

#     return {
#         "curves": curves,
#         "points": points,
#         "xMax": plot_data.get("x_max"),
#         "yMax": plot_data.get("y_max"),
#     }


# def summarize_plot(curves: List[Dict[str, Any]], title: str) -> List[Dict[str, Any]]:
#     """Compact, LLM-safe summary of a set of {name, x, y} curves — a Python
#     port of PlotService.extractChartSummaries ("for chatbot" per its own
#     docstring), used instead of the full curves/points arrays wherever the
#     result needs to stay small enough to sit in the reasoner's prompt.
#     """
#     summaries = []
#     for curve in curves:
#         y = curve.get("y") or []
#         if not y:
#             summaries.append({"name": curve.get("name"), "series": []})
#             continue
#         y_min, y_max = min(y), max(y)
#         avg = sum(y) / len(y)
#         delta = y[-1] - y[0]
#         trend = (
#             "increasing"
#             if delta > 1e-5
#             else "decreasing" if delta < -1e-5 else "stable"
#         )
#         summaries.append(
#             {
#                 "name": curve.get("name"),
#                 "min": round(y_min, 2),
#                 "max": round(y_max, 2),
#                 "avg": round(avg, 2),
#                 "trend": trend,
#             }
#         )
#     return summaries


# def _parse_kpis(state: AgentState, scenario_id: str) -> Dict[str, Dict[str, float]]:
#     """Return KPIs in the format expected by the histogramComparison widget.

#     Output format:
#     {
#         "sustainability_index": {
#             "level": 95,
#             "confidence": 0.52,
#         },
#         "parking": {
#             "level": 100,
#             "confidence": 0.00,
#         },
#         ...
#     }
#     """
#     data = (
#         state.cognitive.context_cache.get(f"scenarios {scenario_id}", {})
#         .get("evaluation_data", {})
#         .get("data", {})
#     )

#     raw_kpis = {
#         "sustainability_index": data.get("sustainability_index", {}),
#         **data.get("sustainability_by_constraint", {}),
#     }

#     parsed = {}

#     for name, value in raw_kpis.items():
#         if isinstance(value, dict):
#             level = value.get("index", value.get("level", value.get("value", 0)))
#             confidence = value.get(
#                 "confidence",
#                 value.get("uncertainty", value.get("ci", 0)),
#             )
#         else:
#             level = value
#             confidence = 0

#         parsed[name] = {
#             "level": round(level * 100),
#             "confidence": confidence * 100,
#         }

#     return parsed
