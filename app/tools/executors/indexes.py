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
    result = get_territorial_index_list.invoke({"tenant": state.tenant})

    return {"indexes": result}


def _summarize_map_features(features: list) -> Dict[str, Any]:
    """Compact, LLM-safe summary of a choropleth's features:
    give the reasoner real, grounded facts (area names, top/bottom values)
    without ever handing it the raw per-feature geometry, which is only
    ever meant to reach the frontend widget."""
    entries = []
    for f in features:
        if not isinstance(f, dict):
            continue
        props = f.get("properties", {}) or {}
        name = props.get("AREA_NAME")
        value = props.get("INDICE")
        if name is not None and isinstance(value, (int, float)):
            entries.append({"area_name": name, "index_value": round(value, 4)})

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

    from app.tools.executor_backend_tools import get_territorial_index_data

    logger.info(
        f"Executing show_territorial_index_map tool for index '{index_id}' "
        f"({start_date} -> {end_date})"
    )

    raw = get_territorial_index_data.invoke(
        {
            "tenant": state.tenant,
            "index": index_id,
            "start_date": start_date,
            "end_date": end_date,
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


EXECUTORS = {
    "get_territorial_index_list": execute_get_territorial_index_list,
    "show_territorial_index_map": execute_show_territorial_index_map,
}
