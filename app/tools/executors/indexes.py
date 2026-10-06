"""Territorial Index tool implementations."""

from typing import Any, Dict
import logging
import time

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def execute_get_territorial_index_list(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute get_territorial_index_list tool.

    Fetches the live list of territorial indexes from the backend
    (id/label/description/years covered) — see
    app.tools.backend_tools.get_territorial_index_list. This is the
    authoritative source for "what indices exist"; the glossary
    (lookup_glossary) only covers the static Territorial Index framework
    vocabulary, not the concrete, ever-changing list of indexes themselves.
    """
    from app.tools.executor_backend_tools import get_territorial_index_list

    logger.info("Executing get_territorial_index_list tool")
    result = get_territorial_index_list.invoke({})
    if isinstance(result, dict):
        indicators = result.get("indicators", [])
        additional_labels = result.get("additional_labels", [])
    else:  # Backward-compatible with a legacy backend response/test fixture.
        indicators = result
        additional_labels = []

    return {"indexes": indicators, "additional_labels": additional_labels}


def _extract_map_entries(features: list, *, round_values: bool = True) -> list:
    """Flat [{area_name, index_value}] for every feature that has both an
    AREA_NAME and a numeric INDICE (same fields, same filtering as the map
    summary below). Features without a value are skipped here; callers that
    need to tell "area exists but has no value" apart from "area doesn't
    exist" use _extract_all_area_names too."""
    entries = []
    for f in features:
        if not isinstance(f, dict):
            continue
        props = f.get("properties", {}) or {}
        name = props.get("AREA_NAME")
        value = props.get("INDICE")
        if (
            name is not None
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            entries.append(
                {
                    "area_name": str(name),
                    "index_value": round(value, 4) if round_values else value,
                }
            )
    return entries


def _extract_all_area_names(features: list) -> list:
    return [
        str((f.get("properties") or {}).get("AREA_NAME"))
        for f in features
        if isinstance(f, dict) and (f.get("properties") or {}).get("AREA_NAME")
    ]


_SEASONALITIES = {
    "weekend",
    "weekdays",
    "festivities",
    "summer-months",
    "winter-months",
}


def _additional_index_params(
    index_id: str,
    indicator: str | None = None,
    start_date_comparison: str | None = None,
    end_date_comparison: str | None = None,
    seasonality: str | None = None,
) -> Dict[str, str]:
    """Validate and return the extra query parameters for combination indexes."""
    normalized_id = (index_id or "").strip().lower()
    if normalized_id == "tasso-variazione":
        missing = [
            name
            for name, value in (
                ("indicator", indicator),
                ("start_date_comparison", start_date_comparison),
                ("end_date_comparison", end_date_comparison),
            )
            if not value or not value.strip()
        ]
        if missing:
            raise ValueError(
                "index_id 'tasso-variazione' requires: " + ", ".join(missing)
            )
        return {
            "indicator": indicator.strip(),
            "start_date_comparison": start_date_comparison.strip(),
            "end_date_comparison": end_date_comparison.strip(),
        }

    if normalized_id == "incidenza-periodo":
        if not indicator or not indicator.strip():
            raise ValueError("index_id 'incidenza-periodo' requires indicator")
        normalized_seasonality = (seasonality or "").strip().lower()
        if normalized_seasonality not in _SEASONALITIES:
            raise ValueError(
                "index_id 'incidenza-periodo' requires seasonality to be one of "
                f"{sorted(_SEASONALITIES)}"
            )
        return {
            "indicator": indicator.strip(),
            "seasonality": normalized_seasonality,
        }

    if any((indicator, start_date_comparison, end_date_comparison, seasonality)):
        raise ValueError(
            "indicator/comparison/seasonality parameters are only valid with "
            "'tasso-variazione' or 'incidenza-periodo'"
        )
    return {}


def _fetch_index_features(
    index_id: str,
    start_date: str,
    end_date: str,
    *,
    spatial_granularity: str = "comune",
    indicator: str | None = None,
    start_date_comparison: str | None = None,
    end_date_comparison: str | None = None,
    seasonality: str | None = None,
):
    """Call the SAME backend endpoint the map widget uses
    (get_territorial_index_map_data -> default/indexes/get_index_data) and
    return (features, min_value, max_value). The geometry is parsed only to
    reach the per-area properties; it never leaves this module."""
    import json

    from app.tools.executor_backend_tools import get_territorial_index_map_data

    params = {
        "index": index_id,
        "start_date": start_date,
        "end_date": end_date,
        "spatial_granularity": spatial_granularity,
        **_additional_index_params(
            index_id,
            indicator,
            start_date_comparison,
            end_date_comparison,
            seasonality,
        ),
    }
    raw = get_territorial_index_map_data.invoke(params)
    geo_data = raw.get("geo_data", {}) if isinstance(raw, dict) else {}
    raw_geojson = geo_data.get("data")
    try:
        parsed = (
            json.loads(raw_geojson) if isinstance(raw_geojson, str) else raw_geojson
        )
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Backend returned invalid GeoJSON for index '{index_id}': {e}"
        )
    features = parsed.get("features", []) if isinstance(parsed, dict) else []
    return features, geo_data.get("min_value"), geo_data.get("max_value")


def _summarize_map_features(features: list) -> Dict[str, Any]:
    """Compact, LLM-safe summary of a choropleth's features:
    give the reasoner real, grounded facts (area names, top/bottom values)
    without ever handing it the raw per-feature geometry, which is only
    ever meant to reach the frontend widget."""
    entries = _extract_map_entries(features)

    entries_sorted = sorted(entries, key=lambda e: e["index_value"], reverse=True)
    return {
        "feature_count": len(features),
        "areas_with_value": len(entries),
        "top_areas": entries_sorted[:5],
        "bottom_areas": list(reversed(entries_sorted[-5:])) if entries_sorted else [],
    }


def execute_show_territorial_index_map(
    state: AgentState,
    index_id: str,
    start_date: str,
    end_date: str,
    spatial_granularity: str = "comune",
    indicator: str | None = None,
    start_date_comparison: str | None = None,
    end_date_comparison: str | None = None,
    seasonality: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Build the 'map' (choropleth) widget for a single territorial index over
    a date range, from live backend geo data.

    The backend returns geo_data.data as a JSON-encoded STRING (not a nested
    object) containing full polygon geometry for every area — far too large
    and useless to ever put in front of the reasoning LLM. It's parsed here
    only to validate it and build a small "map_summary" (feature count,
    top/bottom areas by value) for grounding, then re-serialized as
    geojsonStr exactly the way the frontend widget expects it.

    Field order matters: "success"/"response"/"map_summary" (small, always
    useful) are set BEFORE "assistant_action_data" (which nests the full,
    potentially large GeoJSON string). _format_scratchpad's truncation (see
    app/prompts/react_reasoning.py / app/utils/common.py) keeps whole dict
    keys in insertion order until it runs out of budget, so this ordering
    is what keeps the grounded summary intact in the reasoner's prompt even
    when the heavy geojsonStr has to be partially truncated or dropped.
    """
    import json

    from app.tools.executor_backend_tools import get_territorial_index_map_data

    additional_params = _additional_index_params(
        index_id,
        indicator,
        start_date_comparison,
        end_date_comparison,
        seasonality,
    )

    logger.info(
        f"Executing show_territorial_index_map tool for index '{index_id}' "
        f"({start_date} -> {end_date}), "
        f"spatial_granularity={spatial_granularity}"
    )

    raw = get_territorial_index_map_data.invoke(
        {
            "index": index_id,
            "start_date": start_date,
            "end_date": end_date,
            "spatial_granularity": spatial_granularity,
            **additional_params,
        }
    )

    geo_data = raw.get("geo_data", {}) if isinstance(raw, dict) else {}
    raw_geojson = geo_data.get("data")

    try:
        parsed = (
            json.loads(raw_geojson) if isinstance(raw_geojson, str) else raw_geojson
        )
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Backend returned invalid GeoJSON for index '{index_id}': {e}"
        )

    features = parsed.get("features", []) if isinstance(parsed, dict) else []
    min_value = geo_data.get("min_value")
    max_value = geo_data.get("max_value")

    map_summary = _summarize_map_features(features)
    map_summary.update(
        {
            "index_id": index_id,
            "start_date": start_date,
            "end_date": end_date,
            "spatial_granularity": spatial_granularity,
            **additional_params,
            "min_value": min_value,
            "max_value": max_value,
        }
    )

    action = {
        "type": "SHOW_WIDGET",
        "payload": {
            "widgetName": "map",
            "data": {
                "geojsonStr": json.dumps(parsed, ensure_ascii=False),
                "minValue": min_value,
                "maxValue": max_value,
            },
        },
    }

    return {
        "success": True,
        "response": "Ecco la mappa dell'indice richiesto:",
        "map_summary": map_summary,
        "assistant_action_data": [action],
    }


_PLOT_WIDGETS = {"line": "lineChart", "bar": "barChart"}
_DEFAULT_PLOT_TYPE = "line"
_DEFAULT_GRANULARITY = "mensile"

# Spatial levels. The level is never passed by the caller: it is inferred from
# the kind of territories in `selected_territories` (see
# _resolve_selected_territories).
_LEVEL_COMUNE = "comune"
_LEVEL_MACRO_AREA = "macro_area"
_LEVEL_PROVINCIA = "provincia"

# Entry present in BOTH lists returned by default/indexes/get-spatial-areas
# ({"code": "-1", "name": "Provincia"}): the whole province. Never sent as a
# selected territory (see _resolve_selected_territories).
_PROVINCIA_CODE = "-1"
_PROVINCIA_ALIASES = {
    "1",  # _normalize_name("-1")
    "provincia",
    "provincia di trento",
    "provincia autonoma di trento",
}

_KIND_TO_LEVEL = {"comuni": _LEVEL_COMUNE, "areas": _LEVEL_MACRO_AREA}
_KIND_LABEL = {_LEVEL_COMUNE: "municipalities", _LEVEL_MACRO_AREA: "macro-areas (APT)"}


def _build_territory_index(spatial_areas: Dict[str, Any]) -> list:
    """Flatten the get-spatial-areas payload into
    [{level, code, name, key, code_key}] (the "Provincia" entry is excluded:
    it is handled separately via include_provincia)."""
    entries = []
    for kind, level in _KIND_TO_LEVEL.items():
        for item in (spatial_areas or {}).get(kind, []) or []:
            code = str(item.get("code", "")).strip()
            name = str(item.get("name", "")).strip()
            if not code or not name or code == _PROVINCIA_CODE:
                continue
            entries.append(
                {
                    "level": level,
                    "code": code,
                    "name": name,
                    "key": _normalize_name(name),
                    "code_key": _normalize_name(code),
                }
            )
    return entries


def _resolve_one_territory(requested: str, entries: list):
    """Map one user-typed territory onto exactly one catalogue entry.

    Returns (entry | None, suggestions). Order: exact (normalized) name or
    code match; then a UNIQUE whole-word containment match over BOTH kinds at
    once; otherwise unresolved with a few suggestions. Searching both kinds
    together is deliberate: "San Martino di Castrozza" is contained in a
    municipality AND in an APT name, which is ambiguous and must be reported
    rather than silently picked. Containment is never used when it is not
    unique, so "Trento" resolves to the municipality via the exact pass
    (not to the APT "Trento, Monte Bondone e Altopiano di Pinè")."""
    import difflib

    key = _normalize_name(requested)
    if not key:
        return None, []

    exact = [e for e in entries if key in (e["key"], e["code_key"])]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, [f"{e['name']} ({_KIND_LABEL[e['level']]})" for e in exact[:3]]

    padded = f" {key} "
    contained = [
        e for e in entries if padded in f" {e['key']} " or f" {e['key']} " in padded
    ]
    if len(contained) == 1:
        return contained[0], []
    if contained:
        return None, [f"{e['name']} ({_KIND_LABEL[e['level']]})" for e in contained[:3]]

    by_key = {e["key"]: e for e in entries}
    close = difflib.get_close_matches(key, list(by_key), n=3, cutoff=0.75)
    return None, [
        f"{by_key[k]['name']} ({_KIND_LABEL[by_key[k]['level']]})" for k in close
    ]


def _resolve_selected_territories(
    selected_territories: Any,
    include_provincia: bool,
    spatial_areas: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate the requested territories against the backend catalogue and
    infer the spatial granularity from them.

    Returns {"spatial_granularity", "codes", "names", "include_provincia"}:
    - no territories (or only "Provincia")  -> 'provincia'
    - only municipalities                   -> 'comune'
    - only macro-areas                      -> 'macro_area'
    `codes` are the comune/macro-area IDs the backend filters series on.
    The overall provincial series is NOT requested through `codes`: the
    endpoint only returns one spatial grain per call, so the executor fetches
    it separately when `include_provincia` is True. Raises ValueError for unknown/ambiguous names and for
    mixed municipality + macro-area selections.
    """
    if isinstance(selected_territories, str):
        # NOT split on commas: macro-area names contain them
        # ("Trento, Monte Bondone e Altopiano di Pinè" is a single name).
        selected_territories = [selected_territories]
    requested = [
        t.strip()
        for t in (selected_territories or [])
        if isinstance(t, str) and t.strip()
    ]

    entries = _build_territory_index(spatial_areas)
    resolved, unresolved, seen = [], [], set()
    wants_provincia = bool(include_provincia)

    for name in requested:
        if _normalize_name(name) in _PROVINCIA_ALIASES:
            wants_provincia = True
            continue
        entry, suggestions = _resolve_one_territory(name, entries)
        if entry is None:
            item = {"requested": name}
            if suggestions:
                item["did_you_mean"] = suggestions
            unresolved.append(item)
        elif entry["code"] not in seen:
            seen.add(entry["code"])
            resolved.append(entry)

    if unresolved:
        raise ValueError(
            "Could not match these territories to a unique municipality or "
            f"macro-area: {unresolved}. Ask the user which one they mean."
        )

    levels = {e["level"] for e in resolved}
    if len(levels) > 1:
        by_level = {
            _KIND_LABEL[lvl]: [e["name"] for e in resolved if e["level"] == lvl]
            for lvl in sorted(levels)
        }
        raise ValueError(
            "Municipalities and macro-areas (APT) cannot be mixed in the same "
            f"plot, but the selection contains both: {by_level}. Ask the user "
            "to choose a single level (comuni or macro-aree), optionally "
            "together with the overall provincia."
        )

    if not resolved:
        # Whole province only.
        return {
            "spatial_granularity": _LEVEL_PROVINCIA,
            "codes": [],
            "names": [],
            "code_to_name": {},
            "include_provincia": True,
        }

    return {
        "spatial_granularity": levels.pop(),
        "codes": [e["code"] for e in resolved],
        "names": [e["name"] for e in resolved],
        "code_to_name": {e["code"]: e["name"] for e in resolved},
        "include_provincia": wants_provincia,
    }


_PLOT_CACHE_TTL_SECONDS = 600
_PLOT_CACHE_MAX_ENTRIES = 4


def _plot_cache_key(params: dict) -> str:
    import json

    return json.dumps(params, sort_keys=True, default=str)


def _plot_cache_get(state: AgentState | None, key: str) -> dict | None:
    import copy

    if state is None:
        return None
    cache = state.cognitive.plot_data_cache
    entry = cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _PLOT_CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    # Deep copy: the caller mutates the payload (e.g. appends the provincia
    # series), which must never leak back into the cache.
    return copy.deepcopy(entry["data"])


def _plot_cache_put(state: AgentState | None, key: str, data: dict) -> None:
    import copy

    if state is None:
        return
    cache = state.cognitive.plot_data_cache
    cache[key] = {"ts": time.time(), "data": copy.deepcopy(data)}
    while len(cache) > _PLOT_CACHE_MAX_ENTRIES:
        oldest = min(cache, key=lambda k: cache[k]["ts"])
        del cache[oldest]


def _fetch_plot(tool_fn, params: dict, state: AgentState | None = None) -> dict:
    """Call get-variation-data and return its payload.

    The chart type (line/bar) is NOT part of the backend request, so asking
    for the same data as a different chart sends a byte-identical request —
    which the backend has been seen to answer with an empty payload. To make
    that case robust, successful payloads are cached per session (short TTL)
    and reused for an identical request, so a line -> bar switch doesn't hit
    the backend again. Only non-empty payloads are cached.

    If the backend still returns no series, log the exact request/response
    and retry ONCE.
    """
    key = _plot_cache_key(params)
    cached = _plot_cache_get(state, key)
    if cached is not None:
        logger.info("Reusing cached get-variation-data payload for params=%s", params)
        return cached

    raw = tool_fn.invoke(params)
    if isinstance(raw, dict) and raw.get("series"):
        _plot_cache_put(state, key, raw)
        return raw
    logger.warning(
        "Empty series from get-variation-data; params=%s raw=%s",
        params,
        str(raw)[:500],
    )
    time.sleep(0.5)
    retry = tool_fn.invoke(params)
    n_series = (
        len((retry or {}).get("series") or []) if isinstance(retry, dict) else None
    )
    logger.warning("Retry of get-variation-data returned n_series=%s", n_series)
    if isinstance(retry, dict) and retry.get("series"):
        _plot_cache_put(state, key, retry)
    return retry


# ---------------------------------------------------------------------------
# Plot summary (grounded facts about the plotted series, computed in Python)
# ---------------------------------------------------------------------------
_X_KEYS = ("x", "label", "date", "period", "name")
_Y_KEYS = ("y", "value", "values", "index_value", "indice")
_RAW_X_KEYS = ("labels", "categories", "x", "dates", "periods", "x_axis")
_FLAT_REL_RANGE = 0.01  # range < 1% of the mean magnitude -> "constant"
_PEAK_REL_THRESHOLD = 0.5  # a value is a peak if >= 50% above the series mean


def _as_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _series_points(series: dict, shared_x: list | None) -> list:
    """[(x_label, value)] for one series, tolerating the shapes the backend
    may use: a list of numbers (+ shared x labels), or a list of dicts."""
    data = None
    for key in ("data", "values", "points", "y"):
        if isinstance(series.get(key), list):
            data = series[key]
            break
    if not data:
        return []
    points = []
    for i, item in enumerate(data):
        if isinstance(item, dict):
            x = next((item[k] for k in _X_KEYS if k in item), i)
            y = next(
                (
                    _as_number(item[k])
                    for k in _Y_KEYS
                    if _as_number(item.get(k)) is not None
                ),
                None,
            )
        else:
            x = shared_x[i] if shared_x and i < len(shared_x) else i
            y = _as_number(item)
        if y is not None:
            points.append((str(x), y))
    return points


def _summarize_one_series(label: str, points: list) -> Dict[str, Any]:
    values = [v for _, v in points]
    n = len(values)
    mean = sum(values) / n
    lo_i = min(range(n), key=lambda i: values[i])
    hi_i = max(range(n), key=lambda i: values[i])
    rng = values[hi_i] - values[lo_i]
    scale = max(abs(mean), 1e-12)
    constant = rng / scale < _FLAT_REL_RANGE
    first, last = values[0], values[-1]
    change = last - first
    if constant:
        trend = "constant"
    elif change > 0.05 * rng:
        trend = "increasing"
    elif change < -0.05 * rng:
        trend = "decreasing"
    else:
        trend = "no clear trend (starts and ends at similar values)"
    peaks = []
    if not constant and mean > 0:
        peaks = [
            {"period": points[i][0], "value": round(values[i], 4)}
            for i in range(n)
            if values[i] >= mean * (1 + _PEAK_REL_THRESHOLD)
        ]
    out = {
        "label": label,
        "n_points": n,
        "constant": constant,
        "mean": round(mean, 4),
        "min": {"period": points[lo_i][0], "value": round(values[lo_i], 4)},
        "max": {"period": points[hi_i][0], "value": round(values[hi_i], 4)},
        "first": {"period": points[0][0], "value": round(first, 4)},
        "last": {"period": points[-1][0], "value": round(last, 4)},
        "trend": trend,
    }
    if first not in (0, 0.0):
        out["change_first_to_last_pct"] = round(change / abs(first) * 100, 1)
    if peaks:
        out["peaks"] = peaks[:5]
    return out


def _summarize_plot_series(raw: Any) -> Dict[str, Any] | None:
    """Compact, LLM-safe facts about the plotted series (never the raw
    arrays): per-series min/max/mean/trend/peaks/constant, plus, when there
    are several series, how they differ (ranking by mean, ratio and gap
    between highest and lowest, whether they share peak periods, and how
    similar their shape is). Everything is computed here so the answer can
    only cite real numbers. Returns None (and logs) when the series shape
    is not recognised, so a summary problem never breaks the chart."""
    try:
        if not isinstance(raw, dict):
            return None
        shared_x = next(
            (raw[k] for k in _RAW_X_KEYS if isinstance(raw.get(k), list)), None
        )
        per_series, aligned = [], {}
        for s in raw.get("series") or []:
            if not isinstance(s, dict):
                continue
            label = str(s.get("label", "?")).strip()
            points = _series_points(s, shared_x)
            if not points:
                continue
            per_series.append(_summarize_one_series(label, points))
            aligned[label] = [v for _, v in points]
        if not per_series:
            logger.warning(
                "Plot summary skipped: unrecognised series shape (series keys=%s)",
                (
                    list((raw.get("series") or [{}])[0].keys())
                    if raw.get("series")
                    else None
                ),
            )
            return None

        summary: Dict[str, Any] = {"series": per_series}
        if len(per_series) > 1:
            ranked = sorted(per_series, key=lambda x: x["mean"], reverse=True)
            comparison: Dict[str, Any] = {
                "ranking_by_mean": [
                    {"label": x["label"], "mean": x["mean"]} for x in ranked
                ],
            }
            top, bottom = ranked[0], ranked[-1]
            comparison["gap_highest_vs_lowest"] = round(top["mean"] - bottom["mean"], 4)
            if bottom["mean"] > 0:
                comparison["highest_over_lowest_ratio"] = round(
                    top["mean"] / bottom["mean"], 2
                )
            same_peak = {x["max"]["period"] for x in per_series}
            comparison["peak_period_shared"] = len(same_peak) == 1
            if len(same_peak) == 1:
                comparison["shared_peak_period"] = next(iter(same_peak))
            # Shape similarity: Pearson correlation between the first two
            # series' values (only if same length and non-constant).
            labels = list(aligned)
            a, b = aligned[labels[0]], aligned[labels[1]]
            if len(a) == len(b) and len(a) > 2:
                ma, mb = sum(a) / len(a), sum(b) / len(b)
                da = sum((x - ma) ** 2 for x in a) ** 0.5
                db = sum((x - mb) ** 2 for x in b) ** 0.5
                if da > 0 and db > 0:
                    corr = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)
                    comparison["shape_correlation"] = {
                        "between": [labels[0], labels[1]],
                        "value": round(corr, 2),
                    }
            summary["comparison"] = comparison
        return summary
    except Exception:
        logger.exception("Plot summary failed; continuing without it")
        return None


def execute_show_territorial_index_plot(
    state: AgentState,
    index_id: str,
    start_date: str,
    end_date: str,
    type: str = _DEFAULT_PLOT_TYPE,
    granularity: str = _DEFAULT_GRANULARITY,
    selected_territories: list | None = None,
    include_provincia: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """Build the 'lineChart' / 'barChart' widget for a single territorial
    index over a date range, from live backend data.

    The territorial level is INFERRED from `selected_territories` (only
    municipalities -> 'comune', only macro-areas -> 'macro_area', nothing ->
    'provincia'); it is not an input. Names are resolved against
    default/indexes/get-spatial-areas, mixed municipality/macro-area
    selections are rejected, and `include_provincia` adds the overall
    provincial series to a comune/macro_area plot.

    `selected_territories` is optional in the tool schema (only a
    province-level plot can omit it, which the schema cannot express), so the
    "required unless provincia" rule is enforced here instead.

    `type`, `granularity`, `include_provincia` default here (not only in the
    tool definition) because validate_tool_arguments only enforces *required*
    parameters and never applies ToolParameter.default. `type` shadows the
    builtin only because it is the parameter name exposed to the LLM.
    """
    from app.tools.executor_backend_tools import (
        get_spatial_areas,
        get_territorial_index_plot_data,
    )

    # Validate BEFORE the backend plot call so a bad `type` doesn't cost a
    # request. Also tolerate an LLM passing null/empty/"Line" for the
    # optional parameters instead of omitting them.
    plot_type = (type or _DEFAULT_PLOT_TYPE).strip().lower()

    widget_name = _PLOT_WIDGETS.get(plot_type)
    if widget_name is None:
        raise ValueError(
            f"Unknown plot type '{type}': use one of {sorted(_PLOT_WIDGETS)}"
        )

    # Guard against a stale/hallucinated legacy `spatial_granularity`: the
    # level is now inferred, and silently dropping a comune/macro_area request
    # that comes without territories would plot the whole province instead.
    legacy_level = str(kwargs.get("spatial_granularity") or "").strip().lower()
    has_territories = bool(
        selected_territories
        and (
            [selected_territories]
            if isinstance(selected_territories, str)
            else selected_territories
        )
    )
    if legacy_level in {_LEVEL_COMUNE, _LEVEL_MACRO_AREA} and not has_territories:
        raise ValueError(
            f"A {legacy_level}-level plot requires 'selected_territories' "
            "(the municipalities/macro-areas to show). Ask the user which ones, "
            "or omit the parameter only for a whole-province plot."
        )

    spatial_areas = get_spatial_areas.invoke({})
    selection = _resolve_selected_territories(
        selected_territories, include_provincia, spatial_areas
    )
    spatial_granularity = selection["spatial_granularity"]

    logger.info(
        f"Executing show_territorial_index_plot: {plot_type} plot for index "
        f"'{index_id}' ({start_date} -> {end_date}), granularity={granularity}, "
        f"inferred spatial_granularity={spatial_granularity}, "
        f"territories={selection['names']}, "
        f"include_provincia={selection['include_provincia']}"
    )

    base_params = {
        "index": index_id,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
    }
    raw = _fetch_plot(
        get_territorial_index_plot_data,
        {
            **base_params,
            "spatial_granularity": spatial_granularity,
            "selected_territories": selection["codes"],
        },
        state,
    )

    logger.info(raw)

    missing = []
    if spatial_granularity != _LEVEL_PROVINCIA:
        # The backend silently drops territories it has no series for.
        # IMPORTANT: the returned series identify territories by NAME in
        # series["label"], not by the municipality/macro-area CODE.
        returned = {
            str(s.get("label")).strip()
            for s in (raw.get("series") or [])
            if isinstance(s, dict) and s.get("label") is not None
        }
        returned_keys = {_normalize_name(label) for label in returned}

        missing = [
            name
            for name in selection["names"]
            if _normalize_name(name) not in returned_keys
        ]

        if not returned:
            raise ValueError(
                "The backend returned no series for the selected territories "
                f"{selection['names']} in this period."
            )

        if missing:
            logger.warning(f"No series returned for territories: {missing}")

        # Overall provincial series: get-variation-data returns a single
        # spatial grain per call, so fetch it separately and append it.
        if selection["include_provincia"]:
            prov = _fetch_plot(
                get_territorial_index_plot_data,
                {
                    **base_params,
                    "spatial_granularity": _LEVEL_PROVINCIA,
                    "selected_territories": [],
                },
                state,
            )
            existing = {str(s.get("label")) for s in raw["series"]}
            raw["series"] = list(raw["series"]) + [
                s
                for s in (prov.get("series") or [])
                if str(s.get("label")) not in existing
            ]

    # The payload can be large: log its shape, not its content.
    first = (raw.get("series") or [None])[0] if isinstance(raw, dict) else None
    logger.info(
        "Plot payload for %s: keys=%s, n_series=%s, first_series_keys=%s",
        widget_name,
        list(raw.keys()) if isinstance(raw, dict) else None,
        len(raw.get("series") or []) if isinstance(raw, dict) else None,
        list(first.keys()) if isinstance(first, dict) else None,
    )

    action = {
        "type": "SHOW_WIDGET",
        "payload": {
            "widgetName": widget_name,
            "data": raw,
        },
    }

    series_summary = _summarize_plot_series(raw)

    return {
        "success": True,
        "response": "Ecco il grafico dell'indice richiesto:",
        "series_summary": series_summary,
        "plot_summary": {
            "index_id": index_id,
            "start_date": start_date,
            "end_date": end_date,
            "plot_type": plot_type,
            "granularity": granularity,
            "spatial_granularity": spatial_granularity,
            "selected_territories": selection["names"],
            "include_provincia": selection["include_provincia"],
            "territories_without_data": missing,
        },
        "assistant_action_data": [action],
    }


# ---------------------------------------------------------------------------
# query_territorial_index_values
# ---------------------------------------------------------------------------
_MAX_LISTED_MUNICIPALITIES = 20
_MAX_RANKED_MUNICIPALITIES = 20

_OPERATORS = {
    ">": lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<": lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
}
# Words the LLM (or a user-facing phrase it copies) may use instead of a symbol.
_OPERATOR_ALIASES = {
    "above": ">",
    "higher": ">",
    "greater": ">",
    "over": ">",
    "gt": ">",
    "above_or_equal": ">=",
    "at_least": ">=",
    "gte": ">=",
    "below": "<",
    "lower": "<",
    "less": "<",
    "under": "<",
    "lt": "<",
    "below_or_equal": "<=",
    "at_most": "<=",
    "lte": "<=",
}


def _normalize_name(name: str) -> str:
    """Case-, accent- and punctuation-insensitive key for municipality names
    ("Ville d'Anaunia" == "ville d anaunia", "Cavedine" == "CAVEDINE")."""
    import re
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", name or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def _match_municipality(requested: str, by_key: Dict[str, str]):
    """Map one user-typed name onto a real AREA_NAME. Returns
    (matched_area_name | None, suggestions). Order: exact normalized match,
    then a UNIQUE whole-word containment either way ("Trento" vs "Trento
    (TN)", but never a guess between several), then close spelling matches
    offered only as suggestions — never silently substituted."""
    import difflib

    key = _normalize_name(requested)
    if not key:
        return None, []
    if key in by_key:
        return by_key[key], []

    padded = f" {key} "
    contained = [k for k in by_key if padded in f" {k} " or f" {k} " in padded]
    if len(contained) == 1:
        return by_key[contained[0]], []

    close = difflib.get_close_matches(key, list(by_key), n=3, cutoff=0.75)
    candidates = contained or close
    return None, [by_key[k] for k in candidates[:3]]


def execute_query_territorial_index_values(
    state: AgentState,
    index_id: str,
    start_date: str,
    end_date: str,
    query_type: str,
    municipalities: list | None = None,
    threshold: float | None = None,
    operator: str | None = None,
    count_only: bool = False,
    ranking_order: str | None = None,
    top_n: int | None = 5,
    indicator: str | None = None,
    start_date_comparison: str | None = None,
    end_date_comparison: str | None = None,
    seasonality: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Answer factual questions about a territorial index's per-municipality
    values, from the same endpoint (and the same INDICE/AREA_NAME fields) the
    map widget uses — but WITHOUT producing a widget:

    - query_type="values": the index value of each requested municipality
      over the period (names are matched tolerantly; unknown names are
      reported, with suggestions, instead of being dropped silently).
    - query_type="threshold": every municipality whose value is
      above/below `threshold` (`operator` one of >, >=, <, <=), as a count
      and — unless count_only — a list sorted by value, capped at
      _MAX_LISTED_MUNICIPALITIES entries (the full count is always exact).
        - query_type="ranking": the requested number (five by default) of
            municipalities with the highest or lowest values. If more than that
            number share the extreme value, return all tied municipalities up to
            _MAX_RANKED_MUNICIPALITIES; larger tie groups are reported by count only.

    Python (not the LLM) does all filtering, matching and counting, so the
    numbers in the answer are exactly what the backend returned.
    """
    query_type = (query_type or "").strip().lower()
    if query_type not in {"values", "threshold", "ranking"}:
        raise ValueError(
            f"Unknown query_type '{query_type}': use 'values', 'threshold', or 'ranking'"
        )

    # Validate BEFORE the backend call so a malformed request costs nothing.
    if query_type == "values":
        if isinstance(municipalities, str):
            municipalities = [municipalities]
        municipalities = [
            m.strip()
            for m in (municipalities or [])
            if isinstance(m, str) and m.strip()
        ]
        if not municipalities:
            raise ValueError(
                "query_type 'values' needs at least one municipality name in 'municipalities'"
            )
    elif query_type == "threshold":
        if threshold is None:
            raise ValueError("query_type 'threshold' needs a numeric 'threshold'")
        try:
            threshold = float(str(threshold).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError(f"'threshold' must be a number, got {threshold!r}")
        op_key = (operator or "").strip().lower()
        op_key = _OPERATOR_ALIASES.get(op_key, op_key)
        if op_key not in _OPERATORS:
            raise ValueError(
                f"Unknown operator '{operator}': use one of {sorted(_OPERATORS)}"
            )
    else:
        ranking_order = (ranking_order or "").strip().lower()
        if ranking_order not in {"highest", "lowest"}:
            raise ValueError(
                "query_type 'ranking' requires ranking_order='highest' or 'lowest'"
            )
        if top_n is None:
            top_n = 5
        if isinstance(top_n, bool):
            raise ValueError("'top_n' must be a positive integer")
        try:
            top_n = int(top_n)
        except (TypeError, ValueError):
            raise ValueError("'top_n' must be a positive integer")
        if top_n < 1:
            raise ValueError("'top_n' must be a positive integer")
        if top_n > _MAX_RANKED_MUNICIPALITIES:
            raise ValueError(f"'top_n' cannot exceed {_MAX_RANKED_MUNICIPALITIES}")

    logger.info(
        f"Executing query_territorial_index_values ({query_type}) for index "
        f"'{index_id}' ({start_date} -> {end_date})"
    )

    additional_params = _additional_index_params(
        index_id,
        indicator,
        start_date_comparison,
        end_date_comparison,
        seasonality,
    )
    features, min_value, max_value = _fetch_index_features(
        index_id,
        start_date,
        end_date,
        **additional_params,
    )
    entries = _extract_map_entries(features, round_values=query_type != "ranking")
    all_names = _extract_all_area_names(features)

    base = {
        "success": True,
        "query_type": query_type,
        "index_id": index_id,
        "start_date": start_date,
        "end_date": end_date,
        "areas_with_value": len(entries),
        "min_value": min_value,
        "max_value": max_value,
        **additional_params,
    }

    if not entries:
        return {
            **base,
            "success": False,
            "response": (
                "The backend returned no municipality values for this index "
                "and period."
            ),
        }

    if query_type == "values":
        by_key = {_normalize_name(e["area_name"]): e["area_name"] for e in entries}
        value_of = {e["area_name"]: e["index_value"] for e in entries}
        no_value_keys = {
            _normalize_name(n) for n in all_names if _normalize_name(n) not in by_key
        }

        found, not_found, seen = [], [], set()
        for requested in municipalities:
            matched, suggestions = _match_municipality(requested, by_key)
            if matched is not None:
                if matched not in seen:
                    seen.add(matched)
                    found.append(
                        {"area_name": matched, "index_value": value_of[matched]}
                    )
            elif _normalize_name(requested) in no_value_keys:
                not_found.append(
                    {"requested": requested, "reason": "no value for this period"}
                )
            else:
                item = {"requested": requested, "reason": "municipality not found"}
                if suggestions:
                    item["did_you_mean"] = suggestions
                not_found.append(item)

        return {**base, "values": found, "not_found": not_found}

    if query_type == "ranking":
        ranked = sorted(entries, key=lambda entry: entry["area_name"].casefold())
        ranked = sorted(
            ranked,
            key=lambda entry: entry["index_value"],
            reverse=ranking_order == "highest",
        )
        extreme_value = ranked[0]["index_value"]
        tied_at_extreme = [
            entry for entry in ranked if entry["index_value"] == extreme_value
        ]
        tie_expanded = len(tied_at_extreme) > top_n
        list_omitted = (
            tie_expanded and len(tied_at_extreme) > _MAX_RANKED_MUNICIPALITIES
        )

        if list_omitted:
            municipalities = []
        elif tie_expanded:
            municipalities = tied_at_extreme
        else:
            municipalities = ranked[:top_n]

        return {
            **base,
            "ranking_order": ranking_order,
            "requested_count": top_n,
            "returned_count": len(municipalities),
            "total_areas_considered": len(entries),
            "extreme_value": extreme_value,
            "extreme_value_count": len(tied_at_extreme),
            "ranking_tie_expanded": tie_expanded,
            "ranking_list_omitted": list_omitted,
            "ranked_municipalities": municipalities,
        }

    # ---- threshold ----
    matching = [e for e in entries if _OPERATORS[op_key](e["index_value"], threshold)]
    # Closest-to-the-extreme first: highest first for ">"/">=", lowest first
    # for "<"/"<=".
    matching.sort(key=lambda e: e["index_value"], reverse=op_key in {">", ">="})

    result = {
        **base,
        "threshold": threshold,
        "operator": op_key,
        "matching_count": len(matching),
        "total_areas_considered": len(entries),
    }
    if not count_only:
        listed = matching[:_MAX_LISTED_MUNICIPALITIES]
        result["municipalities"] = listed
        result["list_truncated"] = len(matching) > len(listed)
    return result


EXECUTORS = {
    "get_territorial_index_list": execute_get_territorial_index_list,
    "show_territorial_index_map": execute_show_territorial_index_map,
    "show_territorial_index_plot": execute_show_territorial_index_plot,
    "query_territorial_index_values": execute_query_territorial_index_values,
}
