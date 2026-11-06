"""Structured report document for the "pdf-report" pipeline.

The backend does NOT render the PDF. It builds a plain-data document (this
module, no network and no LLM) that the frontend renders — and prints to PDF —
with its own components, so the plots are the very same Angular widgets the
chat already shows (they are drawn from raw ``plot_data`` that only the
frontend knows how to draw).

What the report covers depends on the ``current_context`` (most specific
wins, see :func:`report_scope`):

* ``scenarios`` present  -> "scenarios": detailed report (changes vs. base,
  narrative with evaluation results, plots) — filled in by the executor.
* else ``proposals``      -> "proposal": each proposal and its scenarios.
* else ``problems``       -> "problem": each problem, its proposals and their
  scenarios.
* empty context           -> "territory": every problem of the territory, its
  proposals and their scenarios.

Scenarios in the first three kinds of report are described from their
metadata and changes only (no evaluations). The base scenario is associated
by default with EVERY proposal, so it is never repeated under each proposal.
In the whole-territory report it is described once, in ``base_scenario``; in the
"problem" and "proposal" reports (and in the detailed "scenarios" report)
``base_scenario`` is None — the reader of a single problem/proposal does not
need the reference scenario described again, and a leading section about it
only pushes the actual content down the document.

Document shape (all keys always present unless noted)::

    {
      "report_type": "territory" | "problem" | "proposal" | "scenarios",
      "title": str,
      "territory": str,
      "generated_at": ISO-8601 str,
      "base_scenario": {scenario node} | None,   # territory report only
      "sections": [problem node | proposal node | scenario node, ...],
      "unassigned_scenarios": [scenario node, ...],   # territory report only
      "warnings": [str, ...],
    }

    problem node:  {"type": "problem", "id", "title", "description",
                    "objective",                     "children": [proposal node, ...], "narrative"}
    proposal node: {"type": "proposal", "id", "title", "description",
                    "status", "context", "impact",
                    "problem": {"id", "name"} | None,
                    "children": [scenario node, ...], "narrative"}
    scenario node: {"type": "scenario", "id", "title", "description",
                    "is_base_scenario": bool,
                    "changes": [str, ...], "narrative"}
                   (the executor adds localized prose to every node and
                    plot widgets to nodes of a "scenarios" report)
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

REPORT_TYPES = ("territory", "problem", "proposal", "scenarios")


def report_scope(current_context: Optional[Dict[str, Any]]) -> str:
    """Which kind of report a context asks for (most specific entity wins)."""
    ctx = current_context or {}
    if ctx.get("scenarios"):
        return "scenarios"
    if ctx.get("proposals"):
        return "proposal"
    if ctx.get("problems"):
        return "problem"
    return "territory"


def related_scenario_ids(proposal: Dict[str, Any]) -> List[str]:
    """Scenario ids listed in a proposal's top-level ``related_scenario_ids``
    (entries may be plain ids or objects)."""
    ids: List[str] = []
    for item in proposal.get("related_scenario_ids") or []:
        sid = item.get("scenario_id") if isinstance(item, dict) else item
        if sid and sid not in ids:
            ids.append(sid)
    return ids


_NUMBER = r"-?\d+(?:\.\d+)?"
_RANGE_RE = re.compile(rf"^({_NUMBER})\s*-\s*({_NUMBER})$")
_NUMBER_RE = re.compile(rf"^{_NUMBER}$")
_EMPTY_VALUES = {"", "none", "null"}


def _number_text(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def _value_text(raw: str) -> str:
    """One side of a backend diff ("0-122", "195", "None", "parking") as
    reader-friendly text: ranges as "0–122", empty/None as "nessun filtro"."""
    text = raw.strip()
    if text.lower() in _EMPTY_VALUES:
        return "nessun filtro"
    match = _RANGE_RE.match(text)
    if match:
        low, high = (_number_text(float(g)) for g in match.groups())
        return f"{low}–{high}"
    if _NUMBER_RE.match(text):
        return _number_text(float(text))
    return text


def _parameter_entry(
    config_indexes: Optional[List[Dict[str, Any]]], name: str
) -> Optional[Dict[str, Any]]:
    """The /configuration entry of a parameter, found by its name (or label)."""
    wanted = name.strip().lower()
    for entry in config_indexes or []:
        if (entry.get("name") or "").strip().lower() == wanted:
            return entry
    for entry in config_indexes or []:
        if (entry.get("label") or "").strip().lower() == wanted:
            return entry
    return None


def scenario_changes(
    scenario: Dict[str, Any], config_indexes: Optional[List[Dict[str, Any]]] = None
) -> List[str]:
    """What a scenario changes with respect to the base scenario, as plain
    text lines with the parameter's human label and unit (from the
    territory's /configuration), e.g. "Posti auto prenotabili: da 195 a 0
    posti". The raw backend name is only a fallback for a parameter missing
    from the configuration."""
    diffs = (scenario.get("extras") or {}).get("index_diffs") or {}
    lines: List[str] = []
    for name, change in diffs.items():
        entry = _parameter_entry(config_indexes, str(name))
        label = (entry or {}).get("label") or str(name)
        unit = ((entry or {}).get("unit") or "").strip()
        before, arrow, after = str(change).partition("->")
        if not arrow:
            lines.append(f"{label}: {_value_text(str(change))}")
            continue
        suffix = f" {unit}" if unit else ""
        lines.append(
            f"{label}: da {_value_text(before)} a {_value_text(after)}{suffix}"
        )
    return lines


def scenario_node(
    scenario: Dict[str, Any],
    base_scenario_id: Optional[str],
    config_indexes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "type": "scenario",
        "id": scenario["scenario_id"],
        "title": scenario.get("name") or scenario["scenario_id"],
        "description": scenario.get("description") or "",
        "is_base_scenario": bool(base_scenario_id)
        and scenario["scenario_id"] == base_scenario_id,
        "changes": scenario_changes(scenario, config_indexes),
    }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _problem_node(problem: Dict[str, Any], children: List[Dict[str, Any]]) -> Dict[str, Any]:
    objective = problem.get("objective") or (problem.get("extras") or {}).get("objective")
    return {
        "type": "problem",
        "id": problem["problem_id"],
        "title": problem.get("name") or problem["problem_id"],
        "description": _text(problem.get("description")),
        "objective": _text(objective),
        "children": children,
    }


def _proposal_node(
    proposal: Dict[str, Any],
    children: List[Dict[str, Any]],
    problems_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    problem = problems_by_id.get(proposal.get("problem_id"))
    return {
        "type": "proposal",
        "id": proposal["proposal_id"],
        "title": proposal.get("name") or proposal["proposal_id"],
        "description": _text(proposal.get("description")),
        "status": _text(proposal.get("status")),
        "context": _text(proposal.get("context")),
        "impact": _text(proposal.get("impact")),
        "problem": (
            {"id": problem["problem_id"], "name": problem.get("name")}
            if problem
            else None
        ),
        "children": children,
    }


def _pick(
    ids: Iterable[str], by_id: Dict[str, Dict[str, Any]], kind: str, warnings: List[str]
) -> List[Dict[str, Any]]:
    """Objects for `ids`, in order; unknown ids become a warning, not an error."""
    picked = []
    seen = set()
    for obj_id in ids:
        if obj_id in seen:
            continue
        seen.add(obj_id)
        if obj_id in by_id:
            picked.append(by_id[obj_id])
        else:
            warnings.append(f"{kind} '{obj_id}' was not found and is not in the report")
    return picked


def build_report_document(
    *,
    territory: str,
    territory_label: str,
    current_context: Optional[Dict[str, Any]],
    problems: List[Dict[str, Any]],
    proposals: List[Dict[str, Any]],
    scenarios: List[Dict[str, Any]],
    base_scenario_id: Optional[str],
    config_indexes: Optional[List[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build the report document from the territory's raw backend lists.

    Pure function: all data is passed in. For the "scenarios" report only the
    skeleton (scenario nodes + the proposals each belongs to) is produced
    here; the executor adds evaluation narrative and plots.
    """
    scope = report_scope(current_context)
    ctx = current_context or {}
    warnings: List[str] = []

    problems_by_id = {p["problem_id"]: p for p in problems}
    proposals_by_id = {p["proposal_id"]: p for p in proposals}
    scenarios_by_id = {s["scenario_id"]: s for s in scenarios}

    def scen_nodes(ids: Iterable[str]) -> List[Dict[str, Any]]:
        # The base scenario is associated with every proposal by default and
        # is described once (base_scenario), so it is not repeated here.
        return [
            scenario_node(scenarios_by_id[sid], base_scenario_id, config_indexes)
            for sid in ids
            if sid in scenarios_by_id and sid != base_scenario_id
        ]

    def proposal_with_scenarios(proposal: Dict[str, Any]) -> Dict[str, Any]:
        return _proposal_node(
            proposal, scen_nodes(related_scenario_ids(proposal)), problems_by_id
        )

    def problem_with_tree(problem: Dict[str, Any]) -> Dict[str, Any]:
        children = [
            proposal_with_scenarios(p)
            for p in proposals
            if p.get("problem_id") == problem["problem_id"]
        ]
        return _problem_node(problem, children)

    sections: List[Dict[str, Any]] = []
    unassigned: List[Dict[str, Any]] = []
    # Only the whole-territory report opens with the reference scenario.
    show_base = scope == "territory"

    if scope == "territory":
        sections = [problem_with_tree(p) for p in problems]
        linked = {sid for p in proposals for sid in related_scenario_ids(p)}
        unassigned = [
            scenario_node(s, base_scenario_id, config_indexes)
            for s in scenarios
            if s["scenario_id"] not in linked and s["scenario_id"] != base_scenario_id
        ]
        title = f"Report – {territory_label}"
    elif scope == "problem":
        chosen = _pick(ctx["problems"], problems_by_id, "Problem", warnings)
        sections = [problem_with_tree(p) for p in chosen]
        title = chosen[0].get("name") if len(chosen) == 1 else f"Report – {territory_label}"
    elif scope == "proposal":
        chosen = _pick(ctx["proposals"], proposals_by_id, "Proposal", warnings)
        sections = [proposal_with_scenarios(p) for p in chosen]
        title = chosen[0].get("name") if len(chosen) == 1 else f"Report – {territory_label}"
    else:  # scenarios: detailed
        chosen = _pick(ctx["scenarios"], scenarios_by_id, "Scenario", warnings)
        sections = []
        for scenario in chosen:
            node = scenario_node(scenario, base_scenario_id, config_indexes)
            node["proposals"] = [
                {"id": p["proposal_id"], "name": p.get("name")}
                for p in proposals
                if scenario["scenario_id"] in related_scenario_ids(p)
            ]
            sections.append(node)
        # The base scenario is part of the report only if it was selected
        # (it is then one of the sections, not a separate leading block).
        title = chosen[0].get("name") if len(chosen) == 1 else f"Report – {territory_label}"

    base_node = None
    if show_base and base_scenario_id and base_scenario_id in scenarios_by_id:
        base_node = scenario_node(scenarios_by_id[base_scenario_id], base_scenario_id, config_indexes)

    if not sections and not unassigned and base_node is None:
        warnings.append("No content was found for this report")

    return {
        "report_type": scope,
        "title": title or f"Report – {territory_label}",
        "territory": territory,
        "territory_label": territory_label,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "base_scenario": base_node,
        "sections": sections,
        "unassigned_scenarios": unassigned,
        "warnings": warnings,
    }
