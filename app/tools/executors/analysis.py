"""Analysis tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

from app.prompts.entity_parsing import get_relatet_context_ids
from app.agent.nodes.utils import _ensure_data_cached
from app.prompts.scanarios import analyze_scenario, generate_summary
from app.prompts.report import generate_report
from app.utils.common import strip_plot_data  # noqa: F401
from app.utils.evaluation_summary import (
    compact_evaluation,
    get_configuration_metadata,
)
from app.utils.configuration_parameters import build_catalog_view, load_indexes
from app.utils.entity_lists import collect_listed_entities, normalize_entity_types

from app.tools.executors.system_utility import execute_lookup_glossary


def execute_get_context_ids(
    state: AgentState,
    user_intent: str,
    entity_types: list | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute get_context_ids tool.

    Reads the lists already fetched by list_available_entities (stored in
    state.cognitive.tool_results) and uses an LLM call to reason over every
    field of every object, returning only the IDs that match the user's intent.

    ``entity_types`` narrows which lists are searched (default: every list
    fetched so far). The legacy ``source_tools`` argument (names of the old
    per-entity list tools) is still honoured when ``entity_types`` is absent,
    so a model continuing a session that started before the tools were merged
    doesn't fail.

    Returns:
        {
            "success": True,
            "context_ids": {
                "problems":  [<id>, ...],
                "proposals": [<id>, ...],
                "scenarios": [<id>, ...],
            },
            # only present if a requested list had not been fetched yet:
            "not_listed_yet": ["proposals"],
        }
    """
    import json
    import re

    if entity_types is None:
        entity_types = kwargs.get("source_tools")

    logger.info(
        f"Executing get_context_ids | intent='{user_intent}' | entity_types={entity_types}"
    )

    # ------------------------------------------------------------------ #
    # Call the LLM and parse
    # ------------------------------------------------------------------ #
    try:
        requested = normalize_entity_types(entity_types)
        listed = collect_listed_entities(state.cognitive.tool_results, requested)
        not_listed_yet = [t for t in requested if t not in listed]

        raw = get_relatet_context_ids(state, user_intent, listed)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        context_ids = json.loads(raw)

        # Ensure all three keys exist and are lists
        for key in ("problems", "proposals", "scenarios"):
            if key not in context_ids or not isinstance(context_ids[key], list):
                context_ids[key] = []

    except Exception as e:
        logger.exception("get_context_ids: could not resolve ids")
        return {
            "success": False,
            "error": str(e),
            "context_ids": {"problems": [], "proposals": [], "scenarios": []},
        }

    logger.info(f"get_context_ids resolved: {context_ids}")

    state.cognitive.current_context = context_ids
    # New topic resolved: drop any cached objects that aren't part of it
    # anymore (see CognitiveState.prune_context_cache).
    state.cognitive.prune_context_cache()
    result = {
        "success": True,
        "context_ids": context_ids,
    }
    if not_listed_yet:
        result["not_listed_yet"] = not_listed_yet
    return result


def execute_get_context_details(
    state: AgentState,
) -> Dict[str, Any]:
    """Execute get_context_details tool.

    Cache-aware: only fetches objects not already in context_cache (see
    CognitiveState.context_cache). Cache is scoped to the current topic and
    kept up to date by prune_context_cache (on topic change) and
    invalidate_cached_object (on edit/delete) — see tool_executor_node.

    Optionally also resolves a "temp" entry in current_context —
    {"creation_session": ..., "evaluation_id": ...} — pointing at a
    temporary, not-yet-saved scenario/evaluation created via
    create_temp_scenario (e.g. for a /agent/tool "summary" call whose
    current_context includes a "temp" entry). When present, its data is
    fetched with a single call to the
    session-scoped evaluation endpoint, cached under "scenarios <id>" just
    like a permanent scenario, and its id is folded into
    current_context["scenarios"] so downstream tools (e.g.
    summary_generation) pick it up without any further changes.
    """
    from app.tools.executor_backend_tools import (
        get_data_from_context,
        get_temp_evaluation_data,
    )

    current_context = state.cognitive.current_context
    cache = state.cognitive.context_cache

    to_fetch = {
        kind: [
            obj_id
            for obj_id in current_context.get(kind, [])
            if f"{kind} {obj_id}" not in cache
        ]
        for kind in ("problems", "proposals", "scenarios")
    }

    logger.info(
        f"Executing get_context_details for context {current_context} "
        f"(already cached, skipping fetch for those; fetching only {to_fetch})"
    )

    if any(to_fetch.values()):
        fetched = get_data_from_context.invoke(
            {"current_context": to_fetch, "territory": state.territory}
        )
        cache.update(fetched.get("retrieved", {}))

    temp = current_context.get("temp")
    if temp:
        creation_session = temp.get("creation_session")
        evaluation_id = temp.get("evaluation_id")
        if not creation_session or not evaluation_id:
            raise ValueError(
                "current_context['temp'] requires both 'creation_session' and "
                "'evaluation_id'"
            )

        # Keyed by (session, evaluation) rather than scenario_id, since the
        # scenario_id itself is only known once the fetch below returns.
        cache_key_temp = f"temp {creation_session} {evaluation_id}"
        if cache_key_temp not in cache:
            logger.info(
                f"Fetching temp evaluation data for session {creation_session}, "
                f"evaluation {evaluation_id}"
            )
            cleaned = get_temp_evaluation_data.invoke(
                {
                    "territory": state.territory,
                    "creation_session": creation_session,
                    "evaluation_id": evaluation_id,
                }
            )
            scenario_id = cleaned["scenario_id"]
            # Strip the heavy raw plot arrays before this enters the
            # long-lived cache (see strip_plot_data). This also fixes a
            # duplication bug: `cleaned` used to be spread into the cache
            # entry AND nested again under "evaluation_data", so plot_data
            # ended up stored twice for the same scenario.
            cached_entry = compact_evaluation(
                cleaned, get_configuration_metadata(state.territory)
            )
            cache[f"scenarios {scenario_id}"] = {
                **cached_entry,
                "evaluation_data": cached_entry,
            }
            # Remember which scenario_id this (session, evaluation) pair
            # resolved to, so a repeat call is a cache hit too.
            cache[cache_key_temp] = {"scenario_id": scenario_id}
        else:
            scenario_id = cache[cache_key_temp]["scenario_id"]

        scenarios_in_context = current_context.setdefault("scenarios", [])
        if scenario_id not in scenarios_in_context:
            scenarios_in_context.append(scenario_id)

    retrieved_context = {
        "retrieved": {
            f"{kind} {obj_id}": cache[f"{kind} {obj_id}"]
            for kind in ("problems", "proposals", "scenarios")
            for obj_id in current_context.get(kind, [])
            if f"{kind} {obj_id}" in cache
        }
    }

    state.cognitive.retrieved_context = retrieved_context

    return retrieved_context


def execute_get_configuration_parameters(
    state: AgentState,
    names: list | str | None = None,
    category: list | str | None = None,
    search: str | None = None,
    detail: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute get_configuration_parameters tool.

    Fetches the backend's /configuration "indexes" and describes them in a
    uniform, kind-aware shape (see app.utils.configuration_parameters):
    name, label, kind (scalar / categorical / distribution), unit, current
    value and allowed values — optionally narrowed to the requested
    names / category / search keywords so the model only reads what it needs.
    """
    from app.tools.executor_backend_tools import get_widgets

    logger.info(
        "Executing get_configuration_parameters tool "
        f"(names={names}, category={category}, search={search}, detail={detail})"
    )

    indexes = load_indexes(get_widgets.invoke({"territory": state.territory}))
    return build_catalog_view(
        indexes, names=names, category=category, search=search, detail=detail
    )


def execute_analyze_scenario_results(
    state: AgentState, query: str, **kwargs
) -> Dict[str, Any]:
    """Execute analyze_scenario_results tool."""

    logger.info(f"Executing analyze_scenario_results tool with query: {query}")

    _ensure_data_cached(state, state.cognitive.current_context)
    answer = analyze_scenario(state, query)
    return {"success": True, "message": answer}


def execute_summary_generation(
    state: AgentState, scenario_ids: list | None = None, **kwargs
) -> Dict[str, Any]:
    scenario_ids = scenario_ids or state.cognitive.current_context.get("scenarios", [])
    if not scenario_ids:
        raise ValueError("No scenario_ids available for summary_generation")
    current_context = {"scenarios": scenario_ids}

    _ensure_data_cached(state, current_context)

    # Pull glossary definitions for the concepts the report needs to explain.
    glossary_result = execute_lookup_glossary(
        state,
        query="constraint capacity, sustainability, uncertainty, problem, proposal, scenario, evaluation",
    )
    glossary_matches = (
        glossary_result.get("matches", []) if glossary_result.get("success") else []
    )

    answer = generate_summary(state, scenario_ids, glossary_matches)
    logger.info(f"Answer: {answer}")
    return {
        "success": True,
        "message": answer,
    }


def _scenario_plots(state: AgentState, scenario_ids: list) -> Dict[str, Any]:
    """Plot widgets for the report, in the SAME shape the chat already sends
    to the frontend ({"widgetName", "data"} = the payload of a SHOW_WIDGET
    action), so the frontend renders them with the widgets it already has.

    Per scenario: loadPlot + capacityPlot. With exactly two scenarios also the
    two comparison widgets (indexComparison, histogramComparison), which are
    defined for a pair. One failing plot never fails the report: it is
    reported in "plots_unavailable" instead.
    """
    from app.tools.executors.analysis_widgets import execute_analysis_widget

    def widget(widget_type: str, ids: list) -> Dict[str, Any] | None:
        try:
            result = execute_analysis_widget(state, widget_type, scenario_ids=ids)
        except Exception:
            logger.exception(f"Report: {widget_type} failed for {ids}")
            return None
        actions = result.get("assistant_action_data") or []
        return actions[0].get("payload") if actions else None

    per_scenario: Dict[str, list] = {}
    unavailable: list = []
    for sid in scenario_ids:
        plots = []
        for widget_type in ("load_plot", "capacity_plot"):
            payload = widget(widget_type, [sid])
            if payload:
                plots.append(payload)
            else:
                unavailable.append({"scenario_id": sid, "plot": widget_type})
        per_scenario[sid] = plots

    comparisons = []
    if len(scenario_ids) == 2:
        for widget_type in ("kpi_comparison", "comparison_plot"):
            payload = widget(widget_type, list(scenario_ids))
            if payload:
                comparisons.append(payload)
            else:
                unavailable.append({"scenario_ids": scenario_ids, "plot": widget_type})

    return {
        "per_scenario": per_scenario,
        "comparisons": comparisons,
        "unavailable": unavailable,
    }


def _report_nodes(document: Dict[str, Any]) -> list:
    nodes = []

    def visit(node: Dict[str, Any]) -> None:
        nodes.append(node)
        for child in node.get("children") or []:
            visit(child)

    if document.get("base_scenario"):
        visit(document["base_scenario"])
    for node in document.get("sections") or []:
        visit(node)
    for node in document.get("unassigned_scenarios") or []:
        visit(node)
    return nodes


def _add_report_content(state: AgentState, document: Dict[str, Any]) -> None:
    """Localize and write all report prose with the assistant, then add charts."""
    scenario_ids = [
        node["id"] for node in _report_nodes(document) if node.get("type") == "scenario"
    ]
    if document["report_type"] == "scenarios" and scenario_ids:
        _ensure_data_cached(state, {"scenarios": scenario_ids})

    glossary_result = execute_lookup_glossary(
        state,
        query="sustainability, uncertainty, capacity, tourism, problem, proposal, scenario",
    )
    glossary_matches = (
        glossary_result.get("matches", []) if glossary_result.get("success") else []
    )
    content = generate_report(state, document, glossary_matches)
    entries = content.get("nodes") or {}
    missing_ids = [
        node["id"]
        for node in _report_nodes(document)
        if not entries.get(node["id"], {}).get("title")
        or not entries.get(node["id"], {}).get("narrative")
    ]
    if missing_ids:
        raise RuntimeError(
            "The assistant did not generate complete report content for: "
            + ", ".join(missing_ids)
        )
    if not content.get("title") or not content.get("territory_label"):
        raise RuntimeError("The assistant returned an incomplete report title")
    if _report_nodes(document) and (
        not content.get("introduction") or not content.get("conclusion")
    ):
        raise RuntimeError("The assistant returned incomplete report prose")

    document["title"] = content["title"]
    document["territory_label"] = content["territory_label"]
    document["introduction"] = content.get("introduction") or ""
    document["conclusion"] = content.get("conclusion") or ""

    def localize(node: Dict[str, Any]) -> None:
        entry = entries[node["id"]]
        node["title"] = entry["title"]
        node["narrative"] = entry["narrative"]
        for key in (
            "description",
            "objective",
            "status",
            "context",
            "impact",
            "problem",
            "changes",
            "proposals",
            "constraints",
        ):
            node.pop(key, None)
        for child in node.get("children") or []:
            localize(child)

    roots = []
    if document.get("base_scenario"):
        roots.append(document["base_scenario"])
    roots.extend(document.get("sections") or [])
    roots.extend(document.get("unassigned_scenarios") or [])
    for node in roots:
        localize(node)

    if document["report_type"] == "scenarios":
        plots = _scenario_plots(state, scenario_ids)
        for node in document["sections"]:
            node["plots"] = plots["per_scenario"].get(node["id"], [])
        document["comparisons"] = plots["comparisons"]
        if plots["unavailable"]:
            document["plots_unavailable"] = plots["unavailable"]
            document["warnings"].append("Some plots could not be retrieved")


def execute_report_generation(
    state: AgentState, current_context: dict | None = None, **kwargs
) -> Dict[str, Any]:
    """Build the structured report document (see app.utils.report_document).

    Works for an EMPTY context too (whole-territory report). The frontend
    renders the document and prints it to PDF; nothing is rendered or stored
    on the server.
    """
    from app.tools.executor_backend_tools import _safe_base_scenario_id
    from app.utils.backend_utils import get_data
    from app.utils.report_document import build_report_document
    from app.utils.territory import display_territory

    if current_context is None:
        current_context = state.cognitive.current_context
    current_context = current_context or {}
    territory = state.territory

    # Human labels/units of the parameters a scenario changes. Failing soft:
    # without them the changes fall back to the raw parameter names.
    config_indexes: list = []
    try:
        from app.tools.executor_backend_tools import get_widgets
        from app.utils.configuration_parameters import load_indexes

        config_indexes = load_indexes(get_widgets.invoke({"territory": territory}))
    except Exception:
        logger.exception("Report: could not load the parameter labels")

    document = build_report_document(
        territory=territory,
        territory_label=display_territory(territory),
        current_context=current_context,
        problems=get_data(f"{territory}/problems"),
        proposals=get_data(f"{territory}/proposals"),
        scenarios=get_data(f"{territory}/scenarios"),
        base_scenario_id=_safe_base_scenario_id(territory),
        config_indexes=config_indexes,
    )
    _add_report_content(state, document)

    logger.info(
        f"Report built: type={document['report_type']}, "
        f"sections={len(document['sections'])}"
    )
    return {"success": True, "message": "Report generated", "report": document}


EXECUTORS = {
    "get_context_ids": execute_get_context_ids,
    "get_context_details": execute_get_context_details,
    "get_configuration_parameters": execute_get_configuration_parameters,
    "analyze_scenario_results": execute_analyze_scenario_results,
    "summary_generation": execute_summary_generation,
    "report_generation": execute_report_generation,
}
