"""
Static definition of the multi-level routing tree.

The top level splits the whole tool surface into four domains (see
TOP_LEVEL_LABELS below). Two of those domains (LOCATION, INDEXES) are
further split into second-level sub-groups so the ReAct reasoner only ever
sees a small, on-topic slice of the tool registry for a given turn instead
of the full list. This is a pure lookup table — no LLM/state logic lives
here, see app.agent.nodes.router for the node that actually drives the
user through it.

IMPORTANT: this routing tree is entirely orthogonal to AgentTier /
ToolDefinition.agent_tier (see tool_schema.py and tool_executor_node). This
module controls which tools are SELECTABLE this turn (scope/navigation);
agent_tier controls the RESPONSE STYLE once a selected tool actually runs,
and whether it needs one-time consent first. A tool's second-level group
here and its agent_tier are independent — e.g. analyze_scenario_results
lives in the LOCATION -> analysis sub-group (so it's only selectable when
the conversation is routed there) but is tagged agent_tier="operative" (so
using it earns an OPERATIVE-style response), while every other tool in
that same sub-group is tagged "executor".

Tool-name sets here MUST be kept in sync with app/tools/definitions/*.py.
There is no dynamic derivation (e.g. from ToolDefinition.tags) because the
grouping the user wants ("location tools" vs "index tools") does not line
up cleanly with any single existing field (ToolCategory mixes read/write
across every domain, tags are free-form) — an explicit table is more
predictable and easier to audit than inferring it.
"""

from typing import Dict, Optional, Set

TOP_SYSTEM_INFO = "system_info"
TOP_LOCATION = "location"
TOP_INDEXES = "indexes"
TOP_GENERAL = "general"

TOP_LEVEL_LABELS: Dict[str, str] = {
    TOP_SYSTEM_INFO: "General system information (what the platform can do, glossary/terminology)",
    TOP_LOCATION: "Problems, proposals, scenarios and analysis for a specific location (Molveno, Altipiano di Fazzon)",
    TOP_INDEXES: "Territorial indexes/indicators for the whole region",
    TOP_GENERAL: "A general, on-topic question not covered by platform data or any other tool",
}

# ---- Level 1: SYSTEM_INFO -------------------------------------------------
_SYSTEM_INFO_TOOLS: Set[str] = {
    "get_system_capabilities",
    "lookup_glossary",
}

# ---- Level 1: GENERAL (delegate to the exploitative tier) -----------------
_GENERAL_TOOLS: Set[str] = {
    "general_question_response",
}

# ---- Level 2 under LOCATION -----------------------------------------------
SUB_PROBLEM = "problem"
SUB_PROPOSAL = "proposal"
SUB_SCENARIO = "scenario"
SUB_ANALYSIS = "analysis"

LOCATION_SUBLEVEL_LABELS: Dict[str, str] = {
    SUB_PROBLEM: "Problems (list, create, edit, delete)",
    SUB_PROPOSAL: "Proposals (list, create, edit, delete)",
    SUB_SCENARIO: "Scenarios (list, preview/evaluate, save, edit, delete)",
    SUB_ANALYSIS: "Analysis, reports and comparison/summary widgets over existing data",
}

# "scenario" and "analysis" are offered as two DISTINCT menu choices (the
# user picks one label or the other), but they resolve to the SAME
# underlying tool set. They aren't actually separable at the tool level:
# evaluating/comparing a scenario (analyze_scenario_results, in the
# "analysis" bucket conceptually) is required by the reasoning prompt to
# always be paired with its charting tool in the same turn
# (show_capacity_plot / comparison_plot, "scenario" bucket) — see
# react_reasoning.py's scenario-analysis guideline. Splitting them into
# disjoint tool sets would silently break that pairing depending on which
# of the two menu labels the user happened to pick, even though both
# describe the same underlying capability from the user's point of view.
_SCENARIO_ANALYSIS_TOOLS: Set[str] = {
    "list_available_scenarios",
    "get_base_scenario",
    "get_configuration_parameters",
    "create_new_temp_scenario",
    "create_new_scenario",
    "edit_scenario",
    "delete_scenario",
    "analyze_scenario_results",
    "comparison_plot",
    "kpi_comparison",
    "show_load_plot",
    "show_capacity_plot",
}

_LOCATION_SUBGROUPS: Dict[str, Set[str]] = {
    SUB_PROBLEM: {
        "list_available_problems",
        "create_new_problem",
        "edit_problem",
        "delete_problem",
    },
    SUB_PROPOSAL: {
        "list_available_proposals",
        "create_new_proposal",
        "edit_proposal",
        "delete_proposal",
    },
    SUB_SCENARIO: _SCENARIO_ANALYSIS_TOOLS,
    SUB_ANALYSIS: _SCENARIO_ANALYSIS_TOOLS,
}

# get_data_from_link, summary_generation, and report_generation are
# deliberately NOT part of any route group above ("ONLY DIRECT CALL FOR
# NOW"): summary_generation/report_generation are already excluded from
# the ReAct tool registry entirely (enabled=False — they're only invoked
# via the separate /agent/tool pipeline), and get_data_from_link, while
# still a regular registered tool, is likewise not yet reachable through
# router-driven chat — for now it's called directly through that same
# other path, not selected by the ReAct reasoner under any of these four
# domains.

# Tools every LOCATION sub-group should keep access to regardless of which
# one was picked: id/context resolution is a cross-cutting step used while
# working on a problem, proposal, *or* scenario (e.g. resolving a proposal's
# parent problem id), so excluding it from, say, the "proposal" sub-group
# would silently break normal argument resolution.
_LOCATION_SHARED_TOOLS: Set[str] = {
    "get_context_ids",
    "get_context_details",
}

# ---- Level 2 under INDEXES -------------------------------------------------
SUB_INDEX_LIST = "index_list"
SUB_INDEX_MAP = "index_map"

INDEXES_SUBLEVEL_LABELS: Dict[str, str] = {
    SUB_INDEX_LIST: "Which territorial indexes exist and what they cover",
    SUB_INDEX_MAP: "Visualize a specific territorial index on the map for a period",
}

_INDEXES_SUBGROUPS: Dict[str, Set[str]] = {
    SUB_INDEX_LIST: {"get_territorial_index_list"},
    SUB_INDEX_MAP: {"get_territorial_index_list", "show_territorial_index_map"},
}


# Top-level domains that have a second level at all. Domains not in this
# dict (SYSTEM_INFO, GENERAL) resolve fully at level 1.
SUBLEVELS: Dict[str, Dict[str, Set[str]]] = {
    TOP_LOCATION: _LOCATION_SUBGROUPS,
    TOP_INDEXES: _INDEXES_SUBGROUPS,
}

SUBLEVEL_LABELS: Dict[str, Dict[str, str]] = {
    TOP_LOCATION: LOCATION_SUBLEVEL_LABELS,
    TOP_INDEXES: INDEXES_SUBLEVEL_LABELS,
}

_TOP_LEVEL_FLAT_TOOLS: Dict[str, Set[str]] = {
    TOP_SYSTEM_INFO: _SYSTEM_INFO_TOOLS,
    TOP_GENERAL: _GENERAL_TOOLS,
}


def has_sublevels(top_level: str) -> bool:
    return top_level in SUBLEVELS


def sublevel_options(top_level: str) -> Dict[str, str]:
    """Sub-group name -> human label for `top_level`, or {} if it has none."""
    return SUBLEVEL_LABELS.get(top_level, {})


# Which guideline module(s) (see app.prompts.react_guidelines) apply for a
# given resolved route. Keys here match GUIDELINE_BLOCKS' keys there. This
# is intentionally a separate lookup from resolve_allowed_tools: guideline
# content is about *how to reason* within a domain, tool allowlisting is
# about *which schemas* the model may pick from — related but not the same
# shape (e.g. SUB_SCENARIO and SUB_ANALYSIS share one guideline module
# because they share one tool set, see _SCENARIO_ANALYSIS_TOOLS above).
_LOCATION_SUBLEVEL_GUIDELINE_GROUPS: Dict[str, str] = {
    SUB_PROBLEM: "problem",
    SUB_PROPOSAL: "proposal",
    SUB_SCENARIO: "scenario_analysis",
    SUB_ANALYSIS: "scenario_analysis",
}


def guideline_groups(top_level: Optional[str], second_level: Optional[str]) -> Set[str]:
    """Which guideline module keys apply for this route. Returns a SET
    (not a single value) because a domain with sub-levels but no
    second_level resolved yet (still routing, or routing was skipped) is
    scoped to the union of every sub-group's tools, so it needs every
    sub-group's guidelines too — a turn shouldn't have a wider tool
    allowlist than the guidance covering it. Returns an empty set for None
    or an unrecognized top_level (caller falls back to every group, same
    "don't restrict what we can't confidently scope" policy as
    resolve_allowed_tools)."""
    if top_level == TOP_SYSTEM_INFO:
        return {"system_info"}
    if top_level == TOP_GENERAL:
        return {"general"}
    if top_level == TOP_INDEXES:
        return {"indexes"}
    if top_level == TOP_LOCATION:
        if second_level in _LOCATION_SUBLEVEL_GUIDELINE_GROUPS:
            return {_LOCATION_SUBLEVEL_GUIDELINE_GROUPS[second_level]}
        return set(_LOCATION_SUBLEVEL_GUIDELINE_GROUPS.values())
    return set()


def resolve_allowed_tools(
    top_level: Optional[str], second_level: Optional[str]
) -> Optional[Set[str]]:
    """Tool-name allowlist for the given route, or None if `top_level` isn't
    resolved yet (caller should fall back to the full known-tools list
    rather than block everything).

    For a domain with sublevels but no second_level chosen yet, returns the
    union of every sub-group in that domain — i.e. "any tool in this
    domain" — which is the right scope while level-2 routing is still being
    decided (see top_level_router_node) and a safe fallback if second-level
    routing is ever skipped.
    """
    if top_level is None:
        return None

    if top_level in _TOP_LEVEL_FLAT_TOOLS:
        return set(_TOP_LEVEL_FLAT_TOOLS[top_level])

    subgroups = SUBLEVELS.get(top_level)
    if subgroups is None:
        # Unknown top_level value (shouldn't happen) — don't restrict.
        return None

    if second_level and second_level in subgroups:
        allowed = set(subgroups[second_level])
        if top_level == TOP_LOCATION:
            allowed |= _LOCATION_SHARED_TOOLS
        return allowed

    # No (valid) second_level yet: union of all sub-groups in this domain.
    allowed: Set[str] = set()
    for tool_names in subgroups.values():
        allowed |= tool_names
    return allowed
