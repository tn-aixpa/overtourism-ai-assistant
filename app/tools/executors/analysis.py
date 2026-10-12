"""Analysis tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

from app.prompts.entity_parsing import get_relatet_context_ids
from app.agent.nodes.utils import _ensure_data_cached
from app.prompts.scanarios import analyze_scenario, generate_summary
from app.prompts.report import generate_report
from app.utils.common import strip_plot_data
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
            cached_entry = strip_plot_data(cleaned)
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


def _entity_label(state: AgentState, kind: str, obj_id: str) -> str:
    """Look up an object's display name in context_cache (falls back to its
    raw id), generalizing _scenario_label above to problems/proposals too."""
    cached = state.cognitive.context_cache.get(f"{kind} {obj_id}", {})
    return cached.get("name") or obj_id


def _index_report_entries(entries: list) -> Dict[str, Any]:
    """Index a list of {"id": ..., ...} chapter dicts from generate_report's
    output by id, tolerating a missing/duplicate/non-dict entry from the LLM
    response (the caller falls back to an empty chapter for any id that
    doesn't show up here)."""
    return {
        entry["id"]: entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("id")
    }


def _escape_for_pdf(text: str) -> str:
    """Escape the handful of characters reportlab's Paragraph mini-markup
    treats specially, so stray '<', '>', '&' in LLM-generated text can't be
    misread as (or break) markup."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_report_pdf(
    state: AgentState, current_context: dict, content: Dict[str, Any]
) -> str:
    """Render the structured content produced by generate_report into an
    actual PDF document on disk and return its path.

    The document's structure (chapter order, headings, whether a chapter
    exists at all) comes entirely from `current_context` and the object
    names already in context_cache — never from the LLM's output — so an
    incomplete or oddly-shaped model response can only leave a chapter's
    body thin, never break the document's layout.
    """
    import os
    import tempfile
    import uuid

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    problem_ids = current_context.get("problems", []) or []
    proposal_ids = current_context.get("proposals", []) or []
    scenario_ids = current_context.get("scenarios", []) or []

    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    chapter_style = ParagraphStyle(
        "ReportChapter", parent=styles["Heading1"], spaceBefore=18, spaceAfter=10
    )
    section_style = ParagraphStyle(
        "ReportSection", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6
    )

    def _paragraphs(text: str) -> list:
        blocks = [b.strip() for b in (text or "").split("\n\n") if b.strip()]
        if not blocks:
            return [Paragraph("No content available.", body_style)]
        return [Paragraph(_escape_for_pdf(b), body_style) for b in blocks]

    story: list = []

    entities = problem_ids + proposal_ids + scenario_ids
    if len(entities) == 1 and scenario_ids:
        title_text = _entity_label(state, "scenarios", scenario_ids[0])
    elif len(entities) == 1 and problem_ids:
        title_text = _entity_label(state, "problems", problem_ids[0])
    elif len(entities) == 1 and proposal_ids:
        title_text = _entity_label(state, "proposals", proposal_ids[0])
    else:
        title_text = "Report"

    story.append(Paragraph(_escape_for_pdf(title_text), styles["Title"]))
    story.append(Spacer(1, 0.6 * cm))

    if content.get("introduction"):
        story.extend(_paragraphs(content["introduction"]))
        story.append(Spacer(1, 0.4 * cm))

    if problem_ids:
        by_id = _index_report_entries(content.get("problems", []))
        for problem_id in problem_ids:
            entry = by_id.get(problem_id, {})
            story.append(
                Paragraph(
                    _escape_for_pdf(_entity_label(state, "problems", problem_id)),
                    chapter_style,
                )
            )
            story.extend(_paragraphs(entry.get("text", "")))

    if proposal_ids:
        by_id = _index_report_entries(content.get("proposals", []))
        for proposal_id in proposal_ids:
            entry = by_id.get(proposal_id, {})
            story.append(
                Paragraph(
                    _escape_for_pdf(_entity_label(state, "proposals", proposal_id)),
                    chapter_style,
                )
            )
            story.extend(_paragraphs(entry.get("text", "")))

    if scenario_ids:
        by_id = _index_report_entries(content.get("scenarios", []))
        story.append(Paragraph("Scenarios", chapter_style))
        for scenario_id in scenario_ids:
            entry = by_id.get(scenario_id, {})
            story.append(
                Paragraph(
                    _escape_for_pdf(_entity_label(state, "scenarios", scenario_id)),
                    section_style,
                )
            )
            story.extend(_paragraphs(entry.get("narrative", "")))

            constraints = entry.get("constraints") or []
            items = []
            for constraint in constraints:
                if not isinstance(constraint, dict):
                    continue
                name = _escape_for_pdf(str(constraint.get("name", "")).strip())
                detail = _escape_for_pdf(str(constraint.get("detail", "")).strip())
                label = f"<b>{name}</b>: {detail}" if name else detail
                if label:
                    items.append(ListItem(Paragraph(label, body_style)))
            if items:
                story.append(ListFlowable(items, bulletType="bullet", leftIndent=18))
                story.append(Spacer(1, 0.3 * cm))

    if content.get("conclusion"):
        story.append(Paragraph("Conclusion", chapter_style))
        story.extend(_paragraphs(content["conclusion"]))

    reports_dir = os.path.join(tempfile.gettempdir(), "digital_twin_reports")
    os.makedirs(reports_dir, exist_ok=True)
    filename = f"report_{state.session_id or 'session'}_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = os.path.join(reports_dir, filename)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title_text,
    )
    doc.build(story)

    return pdf_path


def execute_report_generation(
    state: AgentState, current_context: dict | None = None, **kwargs
) -> Dict[str, Any]:
    current_context = current_context or state.cognitive.current_context

    problem_ids = (current_context or {}).get("problems", []) or []
    proposal_ids = (current_context or {}).get("proposals", []) or []
    scenario_ids = (current_context or {}).get("scenarios", []) or []
    if not (problem_ids or proposal_ids or scenario_ids):
        raise ValueError(
            "No problem, proposal or scenario ids available for report_generation"
        )

    _ensure_data_cached(state, current_context)

    # Pull glossary definitions for the concepts the report needs to explain.
    glossary_result = execute_lookup_glossary(
        state,
        query="constraint capacity, sustainability, uncertainty",
    )
    glossary_matches = (
        glossary_result.get("matches", []) if glossary_result.get("success") else []
    )

    content = generate_report(state, current_context, glossary_matches)
    pdf_path = _build_report_pdf(state, current_context, content)
    logger.info(f"Report PDF generated at: {pdf_path}")

    return {
        "success": True,
        "message": "Report generated",
        # Not yet exposed to the frontend — the file just lives on disk for
        # now (see _build_report_pdf); wire this into the response/route
        # once it's decided how the PDF should reach the client (download
        # link, base64, upload to storage, ...).
        "report_path": pdf_path,
    }


EXECUTORS = {
    "get_context_ids": execute_get_context_ids,
    "get_context_details": execute_get_context_details,
    "get_configuration_parameters": execute_get_configuration_parameters,
    "analyze_scenario_results": execute_analyze_scenario_results,
    "summary_generation": execute_summary_generation,
    "report_generation": execute_report_generation,
}
