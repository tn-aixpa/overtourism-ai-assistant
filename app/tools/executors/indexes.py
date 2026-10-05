"""Territorial Index tool implementations."""

from typing import Any, Dict
import logging

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
_DEFAULT_GRANULARITY = "monthly"
_DEFAULT_SPATIAL_GRANULARITY = "comune"


def execute_show_territorial_index_plot(
    state: AgentState,
    index_id: str,
    start_date: str,
    end_date: str,
    type: str = _DEFAULT_PLOT_TYPE,
    granularity: str = _DEFAULT_GRANULARITY,
    spatial_granularity: str = _DEFAULT_SPATIAL_GRANULARITY,
    **kwargs,
) -> Dict[str, Any]:
    """Build the 'lineChart' / 'barChart' widget for a single territorial
    index over a date range, from live backend data.

    `type`, `granularity` and `spatial_granularity` default here (not only
    in the tool definition) because validate_tool_arguments only enforces
    *required* parameters and never applies ToolParameter.default: an
    optional parameter the LLM omits simply doesn't arrive, so without
    Python-level defaults this would raise a TypeError instead of using the
    documented defaults. `type` shadows the builtin only because it is the
    parameter name exposed to the LLM.
    """
    from app.tools.executor_backend_tools import get_territorial_index_plot_data

    # Validate BEFORE the backend call so a bad `type` doesn't cost a
    # request. Also tolerate an LLM passing null/empty/"Line" for the
    # optional parameters instead of omitting them.
    plot_type = (type or _DEFAULT_PLOT_TYPE).strip().lower()
    granularity = (granularity or _DEFAULT_GRANULARITY).strip().lower()
    spatial_granularity = (
        (spatial_granularity or _DEFAULT_SPATIAL_GRANULARITY).strip().lower()
    )

    widget_name = _PLOT_WIDGETS.get(plot_type)
    if widget_name is None:
        raise ValueError(
            f"Unknown plot type '{type}': use one of {sorted(_PLOT_WIDGETS)}"
        )

    logger.info(
        f"Executing show_territorial_index_plot: {plot_type} plot for index "
        f"'{index_id}' ({start_date} -> {end_date}), granularity={granularity}, "
        f"spatial_granularity={spatial_granularity}"
    )

    raw = get_territorial_index_plot_data.invoke(
        {
            "index": index_id,
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity,
            "spatial_granularity": spatial_granularity,
        }
    )

    # The payload can be large: log its shape, not its content.
    logger.debug(
        "Plot data received (type=%s, keys=%s)",
        raw.__class__.__name__,  # not type(raw): `type` is shadowed above
        list(raw.keys()) if isinstance(raw, dict) else None,
    )

    action = {
        "type": "SHOW_WIDGET",
        "payload": {
            "widgetName": widget_name,
            "data": raw,
        },
    }

    return {
        "success": True,
        "response": "Ecco il grafico dell'indice richiesto:",
        "plot_summary": {
            "index_id": index_id,
            "start_date": start_date,
            "end_date": end_date,
            "plot_type": plot_type,
            "granularity": granularity,
            "spatial_granularity": spatial_granularity,
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
