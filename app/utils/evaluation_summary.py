"""Turn a raw evaluation payload into compact, *labelled* facts for the LLM.

Everything that gives the numbers a meaning lives in the backend's
``/configuration`` response under ``metadata``:

* ``kpi_mapper``  — Italian label of every KPI key (``"constraint level
  parking"`` -> ``"Sostenibilità Parcheggi"``).
* ``mapper``      — Italian label of every constraint name (``"parking"`` ->
  ``"Parcheggi"``), also used for the ``critical constraint`` KPI.
* ``color_map``   — ``[[index, color], ...]``: the colour a plot point gets for
  its ``index`` value (0 = green / sustainable, 1 = red / not sustainable).
* ``plot_mapper`` — axis labels of the load plot (monodimensional) and of the
  capacity plot (bidimensional).

The evaluation data (``/evaluations/{id}/data``) holds the KPIs and the raw
plot points. The raw points are far too heavy for a prompt (and are never kept
in ``context_cache``, see ``app.utils.common.strip_plot_data``), so this module
reduces them to a small summary — e.g. how many points are red — computed in
Python so the LLM only has to report figures, never to count.

No I/O and no agent imports: unit-testable with the sample payloads.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Metadata access (cached per territory, it practically never changes)
# --------------------------------------------------------------------------

_METADATA_TTL_SECONDS = 300
_metadata_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def get_configuration_metadata(territory: str) -> Dict[str, Any]:
    """The ``metadata`` block of ``{territory}/configuration`` ({} on failure).

    Failing soft is deliberate: without labels the summary degrades to raw
    keys, which is still better than no summary.
    """
    import logging

    from app.utils.backend_utils import get_data

    now = time.monotonic()
    hit = _metadata_cache.get(territory)
    if hit and now - hit[0] < _METADATA_TTL_SECONDS:
        return hit[1]

    try:
        payload = get_data(f"{territory}/configuration")
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    except Exception as exc:  # network / auth / shape problems
        logging.getLogger(__name__).warning(
            f"Could not load /configuration metadata for {territory}: {exc}"
        )
        return {}

    _metadata_cache[territory] = (now, metadata)
    return metadata


# --------------------------------------------------------------------------
# KPIs
# --------------------------------------------------------------------------


def _constraint_label(name: Any, metadata: Dict[str, Any]) -> str:
    mapper = metadata.get("mapper") or {}
    return mapper.get(name, str(name))


def _round(value: Any, digits: int = 2) -> Any:
    return round(value, digits) if isinstance(value, (int, float)) else value


def _it(number: Any, digits: int = 1) -> str:
    """Italian number format (decimal comma), e.g. 91.7169 -> '91,7'."""
    return f"{number:.{digits}f}".replace(".", ",")


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _kpi_result_text(value: Any, metadata: Dict[str, Any]) -> str:
    """Human-readable Italian rendering of one KPI's content.

    The model receives THIS text, never the backend's field names, so it
    cannot echo technical names such as 'level' or 'confidence'. Known
    fields: level (0-100 -> %), confidence (margin in percentage points),
    name (constraint -> UI label), value (plain number; its unit is already
    part of the KPI label), share (fraction 0-1 -> %). Unknown fields are
    appended as 'campo: valore' so no information is lost.
    """
    if not isinstance(value, dict):
        return _it(value, 2) if _is_num(value) else str(value)

    main: List[str] = []
    extra: List[str] = []
    if "name" in value:
        main.append(_constraint_label(value["name"], metadata))
    if _is_num(value.get("level")):
        main.append(f"{_it(value['level'])}%")
    if _is_num(value.get("value")):
        main.append(_it(value["value"], 1))
    if _is_num(value.get("share")):
        main.append(f"pari al {_it(value['share'] * 100)}% del totale")
    if _is_num(value.get("confidence")):
        extra.append(
            f"incertezza di ±{_it(value['confidence'])} punti percentuali"
        )
    known = {"name", "level", "value", "share", "confidence"}
    for field, content in value.items():
        if field not in known:
            extra.append(f"{field}: {_it(content, 2) if _is_num(content) else content}")

    text = ", ".join(main)
    if extra:
        text += f" ({'; '.join(extra)})" if text else "; ".join(extra)
    return text


def label_kpis(kpis: Dict[str, Any], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """EVERY KPI as ``{label, result[, role]}``, in the order the UI shows them.

    ``label`` comes from ``kpi_mapper`` (raw key if missing) and ``result`` is
    a ready-to-quote Italian phrase (see _kpi_result_text). Ordering follows
    ``kpi_mapper``; KPIs absent from it are appended, none is dropped.
    """
    if not isinstance(kpis, dict):
        return []

    kpi_mapper = metadata.get("kpi_mapper") or {}
    ordered_keys = [k for k in kpi_mapper if k in kpis]
    ordered_keys += [k for k in kpis if k not in ordered_keys]

    roles = {"sustainability_level": "overall", "critical constraint": "critical"}
    labelled = []
    for key in ordered_keys:
        entry = {
            "label": kpi_mapper.get(key, key),
            "result": _kpi_result_text(kpis[key], metadata),
        }
        if key in roles:
            entry["role"] = roles[key]
        labelled.append(entry)
    return labelled


# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------

_NAMED_COLORS = {
    "green": (0, 128, 0),
    "yellow": (255, 255, 0),
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
    "white": (255, 255, 255),
}

_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)")


def _parse_color(color: Any) -> Optional[Tuple[float, float, float]]:
    text = str(color).strip().lower()
    match = _RGB_RE.match(text)
    if match:
        return tuple(float(g) for g in match.groups())  # type: ignore[return-value]
    if text in _NAMED_COLORS:
        return tuple(float(c) for c in _NAMED_COLORS[text])  # type: ignore[return-value]
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return tuple(float(int(text[i : i + 2], 16)) for i in (1, 3, 5))  # type: ignore[return-value]
    return None


def _color_stops(metadata: Dict[str, Any]) -> List[Tuple[float, Tuple[float, ...]]]:
    stops = []
    for item in metadata.get("color_map") or []:
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            continue
        rgb = _parse_color(item[1])
        if rgb is not None and isinstance(item[0], (int, float)):
            stops.append((float(item[0]), rgb))
    return sorted(stops, key=lambda s: s[0])


def color_at(index: float, stops: List[Tuple[float, Tuple[float, ...]]]):
    """Linear interpolation of the colour map — what the plot draws."""
    if not stops:
        return None
    if index <= stops[0][0]:
        return stops[0][1]
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if index <= x1:
            t = 0 if x1 == x0 else (index - x0) / (x1 - x0)
            return tuple(a + (b - a) * t for a, b in zip(c0, c1))
    return stops[-1][1]


def classify_color(rgb: Tuple[float, ...]) -> str:
    """'green' | 'yellow' | 'red' for a colour of the (green-yellow-red) map.

    Yellow is the saturated middle (low blue channel, red ~ green); otherwise
    the dominant of red/green decides. The map's pale tints (e.g.
    rgb(230, 250, 225)) are the light end of green / red and keep that class.
    """
    r, g, b = rgb
    if b < 120 and abs(r - g) < 40:
        return "yellow"
    return "red" if r > g else "green"


def color_class_ranges(metadata: Dict[str, Any]) -> Dict[str, Tuple[float, float]]:
    """Index interval [low, high] each colour class covers on the colour map."""
    stops = _color_stops(metadata)
    if not stops:
        return {}
    ranges: Dict[str, List[float]] = {}
    steps = 1000
    for i in range(steps + 1):
        idx = i / steps
        cls = classify_color(color_at(idx, stops))
        lo_hi = ranges.setdefault(cls, [idx, idx])
        lo_hi[0] = min(lo_hi[0], idx)
        lo_hi[1] = max(lo_hi[1], idx)
    return {cls: (lo, hi) for cls, (lo, hi) in ranges.items()}


# --------------------------------------------------------------------------
# Plot points
# --------------------------------------------------------------------------


def _stats(values: List[float]) -> Optional[Dict[str, float]]:
    if not values:
        return None
    return {
        "min": _round(min(values)),
        "max": _round(max(values)),
        "mean": _round(sum(values) / len(values)),
    }


def _axis_label(plot_mapper: Dict[str, Any], dim: str, axis: str) -> Optional[str]:
    return ((plot_mapper.get(dim) or {}).get(axis) or {}).get("label")


def summarize_points(points: List[Dict[str, Any]], metadata: Dict[str, Any]) -> Dict:
    """Counts by colour class plus basic stats over the plotted points."""
    stops = _color_stops(metadata)
    counts = {"green": 0, "yellow": 0, "red": 0}
    indexes: List[float] = []

    for point in points:
        idx = point.get("index") if isinstance(point, dict) else None
        if not isinstance(idx, (int, float)):
            continue
        indexes.append(float(idx))
        if stops:
            counts[classify_color(color_at(float(idx), stops))] += 1

    total = len(indexes)
    summary: Dict[str, Any] = {"total_points": total}
    if total and stops:
        summary["points_by_color"] = {
            cls: {"count": n, "percent": _round(100 * n / total, 1)}
            for cls, n in counts.items()
        }
    summary["index_value"] = _stats(indexes)

    for field in ("usage", "usage_uncertainty", "tourists", "excursionists"):
        values = [
            float(p[field])
            for p in points
            if isinstance(p, dict) and isinstance(p.get(field), (int, float))
        ]
        if values:
            summary[field] = _stats(values)
    return summary


def summarize_plot_data(
    plot_data: Dict[str, Any], metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Compact, labelled description of what the load / capacity plots show.

    Safe on partial payloads: anything missing is simply left out.
    """
    if not isinstance(plot_data, dict):
        return {}

    plot_mapper = metadata.get("plot_mapper") or {}
    out: Dict[str, Any] = {}

    ranges = color_class_ranges(metadata)
    if ranges:
        out["color_legend"] = {
            "rule": (
                "Each plotted point is one simulated day. Its colour comes from "
                "its 'index' (0 = green/sustainable, ~0.5 = yellow/partially "
                "sustainable, 1 = red/not sustainable) = probability that the "
                "day exceeds the capacity."
            ),
            "index_range_by_color": {
                cls: [_round(lo, 3), _round(hi, 3)] for cls, (lo, hi) in ranges.items()
            },
        }

    points = plot_data.get("points")
    if isinstance(points, dict):
        out["points"] = {
            group: summarize_points(items, metadata)
            for group, items in points.items()
            if isinstance(items, list)
        }
    elif isinstance(points, list):
        out["points"] = {"all": summarize_points(points, metadata)}

    out["axes"] = {
        "load_plot": {
            "x": _axis_label(plot_mapper, "monodimensional", "x"),
            "y": _axis_label(plot_mapper, "monodimensional", "y"),
        },
        "capacity_plot": {
            "x": _axis_label(plot_mapper, "bidimensional", "x"),
            "y": _axis_label(plot_mapper, "bidimensional", "y"),
        },
    }

    capacities = plot_data.get("capacity_mean_by_constraint")
    if isinstance(capacities, dict):
        out["mean_capacity_by_constraint"] = {
            _constraint_label(name, metadata): _round(value, 1)
            for name, value in capacities.items()
        }
    for key in ("capacity_mean", "x_max", "y_max"):
        if key in plot_data:
            out[key] = _round(plot_data[key], 1)

    curves = plot_data.get("constraint_curves")
    if isinstance(curves, dict):
        out["constraint_lines_in_capacity_plot"] = [
            _constraint_label(name, metadata) for name in curves
        ]
    return out


# --------------------------------------------------------------------------
# What actually enters the long-lived cache / the prompts
# --------------------------------------------------------------------------


def compact_evaluation(
    eval_data: Dict[str, Any], metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """``clean_scenario()`` output -> the slim, labelled shape kept in
    ``context_cache``: raw ``plot_data`` dropped, replaced by ``plot_summary``,
    and the KPIs also available as a labelled list (``kpis_labelled``)."""
    if not isinstance(eval_data, dict):
        return eval_data

    slim = {k: v for k, v in eval_data.items() if k != "plot_data"}
    slim["kpis_labelled"] = label_kpis(eval_data.get("data", {}), metadata)
    plot_summary = summarize_plot_data(eval_data.get("plot_data", {}), metadata)
    if plot_summary:
        slim["plot_summary"] = plot_summary
    return slim


def build_legend(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Labels worth showing next to evaluation data in an analysis prompt."""
    return {
        "constraint_labels": metadata.get("mapper") or {},
        "kpi_labels": metadata.get("kpi_mapper") or {},
        "plot_axes": metadata.get("plot_mapper") or {},
    }
