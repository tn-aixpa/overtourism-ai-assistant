"""
Tool execution node for the agentic system (Acting half of the ReAct loop).

Executes the single tool the reasoner just selected ("Action"), records the
result on the scratchpad ("Observation"), and routes back to
react_reasoner_node so it can decide the next step with that observation in
hand. This node handles the actual tool invocation and error handling.
"""

import logging
from typing import Any, Dict, Callable
from langgraph.types import Command

from app.agent.state import AgentState, ReActStep
from app.agent.events import publish_action
from app.agent.nodes.utils import (
    _resolve_referenced_id,
    _missing_required_params,
    _trim_tool_results,
    _ensure_data_cached,
)
from app.tools.tool_registry import get_tool_registry
from app.tools.tool_schema import ToolDefinition
from app.prompts.entity_parsing import get_relatet_context_ids
from app.prompts.scanarios import analyze_scenario, generate_summary
from app.prompts.report import generate_report
from app.utils.backend_entities_parsing import _parse_kpis

logger = logging.getLogger(__name__)

# Tools that mutate platform data and therefore require an explicit user
# confirmation (recap of the data about to be submitted) before they run.
CONFIRMATION_REQUIRED_TOOLS = {
    "create_new_problem",
    "create_new_proposal",
    "create_new_scenario",
    "edit_problem",
    "edit_proposal",
    "edit_scenario",
    "delete_problem",
    "delete_proposal",
    "delete_scenario",
}


# Maps a tool to the (parameter, current_context key) used to auto-resolve
# an ID once get_context_ids has run earlier this turn. Covers both
# "parent" references (e.g. a new proposal's problem_id) and "target"
# references (e.g. the problem_id of the problem being edited/deleted) —
# resolution logic is identical in both cases: only fill in when exactly
# one candidate exists in current_context, otherwise leave it for the
# missing-parameter check to catch.
# Maps a mutating tool to the (parameter, context_cache kind) of the object
# it just changed, so tool_executor_node can evict that object's stale
# cache entry right after a successful run (see
# CognitiveState.invalidate_cached_object). Only covers edit/delete: a
# create_* tool produces a brand-new id that can't already be cached.
_CACHE_INVALIDATION_MAP = {
    "edit_problem": ("problem_id", "problems"),
    "delete_problem": ("problem_id", "problems"),
    "edit_proposal": ("proposal_id", "proposals"),
    "delete_proposal": ("proposal_id", "proposals"),
    "edit_scenario": ("scenario_id", "scenarios"),
    "delete_scenario": ("scenario_id", "scenarios"),
}


def execute_selected_tool(
    tool_name: str,
    tool_arguments: Dict[str, Any],
    state: AgentState,
    allow_disabled: bool = False,
) -> Dict[str, Any]:
    """
    Execute a tool with the given arguments.

    Handles dispatching to tool-specific implementations.
    Returns the tool result.

    `allow_disabled`: some tools (e.g. summary_generation) are registered
    with enabled=False purely to keep them out of the normal ReAct
    allowlist (see ToolRegistry.get_all_known_tools), while still being
    callable explicitly — e.g. from the /agent/tool pipeline endpoint. Set
    this to True in that kind of explicit, non-ReAct invocation path.
    """
    logger.info(f"Executing tool: {tool_name} with args: {tool_arguments}")

    # Get the tool definition
    registry = get_tool_registry()
    tool_def = registry.get_tool(tool_name)

    if not tool_def:
        raise ValueError(f"Tool '{tool_name}' not found in registry")

    if not tool_def.enabled and not allow_disabled:
        raise ValueError(f"Tool '{tool_name}' is disabled")

    validate_tool_arguments(tool_def, tool_arguments)

    # Get the executor function for this tool
    # For now, this is a placeholder that we'll fill in with actual implementations
    executor = get_tool_executor(tool_name)

    if executor is None:
        raise NotImplementedError(f"Tool executor for '{tool_name}' not implemented")

    # Execute the tool
    try:
        result = executor(state, **tool_arguments)
        return {
            "success": True,
            "output": result,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
        return {
            "success": False,
            "output": None,
            "error": str(e),
        }


def validate_tool_arguments(tool_def: ToolDefinition, args: dict) -> None:

    for param in tool_def.parameters:
        if param.required:
            if param.name not in args:
                raise ValueError(
                    f"Missing required parameter '{param.name}' for tool '{tool_def.name}'"
                )

            value = args[param.name]
            if value is None:
                raise ValueError(f"Parameter '{param.name}' cannot be null")

            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Parameter '{param.name}' cannot be empty")


def get_tool_executor(tool_name: str) -> Callable | None:
    """
    Get the executor function for a tool.

    This dispatcher maps tool names to their implementation functions.
    """
    # Map tool names to executor functions
    executors: Dict[str, Callable] = {
        # System
        "get_system_capabilities": execute_get_system_capabilities,
        # Data retrieval
        "list_available_problems": execute_list_available_problems,
        "list_available_proposals": execute_list_available_proposals,
        "list_available_scenarios": execute_list_available_scenarios,
        "get_context_ids": execute_get_context_ids,
        "get_context_details": execute_get_context_details,
        "get_data_from_link": execute_get_data_from_link,
        "get_base_scenario": execute_get_base_scenario,
        "get_configuration_parameters": execute_get_configuration_parameters,
        # Interaction
        "analyze_scenario_results": execute_analyze_scenario_results,
        "comparison_plot": execute_comparison_plot,
        "kpi_comparison": execute_kpi_comparison,
        "show_capacity_plot": execute_show_capacity_plot,
        "show_load_plot": execute_show_load_plot,
        # Internal-only (see create_summary_generation_tool)
        "summary_generation": execute_summary_generation,
        "report_generation": execute_report_generation,
        # Creation stubs
        "create_new_problem": execute_create_new_problem,
        "create_new_proposal": execute_create_new_proposal,
        "create_new_temp_scenario": execute_create_new_temp_scenario,
        "create_new_scenario": execute_create_new_scenario,
        # Editing stubs
        "edit_problem": execute_edit_problem,
        "edit_proposal": execute_edit_proposal,
        "edit_scenario": execute_edit_scenario,  # not yet implemented
        # Deletion stubs
        "delete_problem": execute_delete_problem,
        "delete_proposal": execute_delete_proposal,
        "delete_scenario": execute_delete_scenario,
        # Utility
        "lookup_glossary": execute_lookup_glossary,
    }

    return executors.get(tool_name)


def tool_executor_node(state: AgentState) -> Command:
    """
    Acting half of the ReAct loop: executes the single tool the reasoner
    just selected (state.cognitive.selected_tool / tool_arguments), records
    an Observation on the scratchpad, and routes back to react_reasoner so
    it can decide the next Thought/Action with that observation in hand.

    Confirmation-requiring tools pause here and route to WAIT_USER_INPUT;
    when the user confirms, the waiting node resumes here to actually run
    the tool.
    """
    tool_name = state.cognitive.selected_tool
    tool_arguments = state.cognitive.tool_arguments or {}
    thought = state.cognitive.pending_thought

    if not tool_name:
        logger.warning("tool_executor reached with no pending action")
        return Command(update=state, goto="generate_output_message")

    logger.info(
        f"Executing action [step {len(state.cognitive.scratchpad) + 1}]: "
        f"{tool_name} with args: {tool_arguments}"
    )

    # Try to fill in a parent id (problem_id / proposal_id) that the user
    # referred to by name rather than by literal ID, using whatever
    # get_context_ids already resolved earlier this turn.
    tool_arguments = _resolve_referenced_id(state, tool_name, tool_arguments)
    state.cognitive.tool_arguments = tool_arguments

    # ---- Required-parameter check ----
    # Validate BEFORE asking for confirmation: confirming a recap that is
    # missing required data (and only failing afterwards) is confusing and
    # wastes a turn. If something required is still missing, ask for it
    # directly instead of entering the confirmation flow.
    registry = get_tool_registry()
    tool_def = registry.get_tool(tool_name)
    if tool_def:
        missing = _missing_required_params(tool_def, tool_arguments)
        if missing:
            logger.info(f"'{tool_name}' missing required params: {missing}")
            state.cognitive.tool_confirmed = False
            state.cognitive.tool_confirmation_needed = False
            readable = ", ".join(missing)
            state.cognitive.messages_to_include = [
                f"To proceed I still need the following: {readable}. Could you provide it?"
            ]
            return Command(update=state, goto="generate_output_message")

    # ---- Confirmation gate ----
    # Creation/edit/delete tools must never run silently: the first time we
    # reach one of them, stop and ask the user to confirm a recap of the
    # data that is about to be submitted. Only proceed once the user has
    # explicitly confirmed (tool_confirmed is set by WAIT_USER_INPUT after a
    # "yes").
    if tool_name in CONFIRMATION_REQUIRED_TOOLS and not state.cognitive.tool_confirmed:
        logger.info(f"Pausing '{tool_name}' for user confirmation")
        state.cognitive.tool_confirmation_needed = True
        return Command(update=state, goto="WAIT_USER_INPUT")

    # Confirmation (if it was required) has been consumed for this step.
    state.cognitive.tool_confirmed = False
    state.cognitive.tool_confirmation_needed = False

    publish_action(state.session_id, tool_name)

    try:
        result = execute_selected_tool(tool_name, tool_arguments, state)

        state.cognitive.tool_result = result

        # ---- Persist result in tool_results dict (long-term memory) ----
        # Use a unique key: tool_name, or tool_name__N if already present.
        result_key = tool_name
        collision = 0
        while result_key in state.cognitive.tool_results:
            collision += 1
            result_key = f"{tool_name}__{collision}"
        state.cognitive.tool_results[result_key] = result
        _trim_tool_results(state)

        # ---- Record the Observation on this turn's scratchpad ----
        state.cognitive.scratchpad.append(
            ReActStep(
                thought=thought,
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                observation=result,
                observation_key=result_key,
            )
        )

        state.add_trace(
            "tool_execution",
            tool_name,
            {"result_key": result_key, "result": result},
        )

        logger.info(f"Tool '{tool_name}' result stored as '{result_key}'")

        if not result["success"]:
            state.cognitive.error_details = result.get("error", "Unknown error")
            return Command(update=state, goto="error")

        tool_output = (
            result.get("output", {}) if isinstance(result.get("output"), dict) else {}
        )
        assistant_actions = tool_output.get("assistant_action_data")
        if assistant_actions:
            existing = state.assistant_action_data or []
            if isinstance(assistant_actions, list):
                state.assistant_action_data = existing + assistant_actions
            else:
                state.assistant_action_data = existing + [assistant_actions]

        # The object this tool just edited/deleted may still be cached from
        # an earlier get_context_details — evict it so any later lookup
        # re-fetches fresh data instead of serving the stale copy.
        invalidation = _CACHE_INVALIDATION_MAP.get(tool_name)
        if invalidation:
            param_name, kind = invalidation
            obj_id = tool_arguments.get(param_name)
            if obj_id:
                state.cognitive.invalidate_cached_object(kind, obj_id)

        # Clear the pending-action slot now that it has been executed, then
        # hand back to the reasoner for the next Thought/Action decision.
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.pending_thought = ""
        return Command(update=state, goto="react_reasoner")

    except Exception as e:
        logger.error(f"Exception in tool executor: {e}", exc_info=True)
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================


def execute_get_system_capabilities(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute get_system_capabilities tool."""
    from app.utils.system_capabilities import SYSTEM_DESCRIPTION

    logger.info("Executing get_system_capabilities tool")

    return {
        "success": True,
        "system_description": SYSTEM_DESCRIPTION,
    }


def execute_list_available_problems(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_problems tool."""
    from app.tools.backend_tools import get_all_problems

    logger.info("Executing list_available_problems tool")
    result = get_all_problems.invoke({"tenant": state.tenant})

    return result


def execute_list_available_proposals(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_proposals tool."""
    from app.tools.backend_tools import get_all_proposals

    logger.info("Executing list_available_proposals tool")
    result = get_all_proposals.invoke({"tenant": state.tenant})

    return result


def execute_list_available_scenarios(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_scenarios tool."""
    from app.tools.backend_tools import get_all_scenarios

    logger.info("Executing list_available_scenarios tool")
    result = get_all_scenarios.invoke({"tenant": state.tenant})

    return result


def execute_get_context_ids(
    state: AgentState,
    user_intent: str,
    source_tools: list,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute get_context_ids tool.

    Reads raw list data that was already collected by list_available_problems /
    list_available_proposals / list_available_scenarios (stored in
    state.cognitive.tool_results) and uses an LLM call to reason over every
    field of every object, returning only the IDs that match the user's intent.

    Returns:
        {
            "success": True,
            "context_ids": {
                "problems":  [<id>, ...],
                "proposals": [<id>, ...],
                "scenarios": [<id>, ...],
            }
        }
    """
    import json
    import re

    logger.info(
        f"Executing get_context_ids | intent='{user_intent}' | sources={source_tools}"
    )

    # ------------------------------------------------------------------ #
    # 3. Call the LLM and parse
    # ------------------------------------------------------------------ #
    try:
        raw = get_relatet_context_ids(state, user_intent, source_tools)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        context_ids = json.loads(raw)

        # Ensure all three keys exist and are lists
        for key in ("problems", "proposals", "scenarios"):
            if key not in context_ids or not isinstance(context_ids[key], list):
                context_ids[key] = []

    except Exception as e:
        logger.exception("get_context_ids: failed to parse LLM response")
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
    return {
        "success": True,
        "context_ids": context_ids,
    }


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
    create_temp_scenario (e.g. for the /agent/tool "summary-temp"
    pipeline). When present, its data is fetched with a single call to the
    session-scoped evaluation endpoint, cached under "scenarios <id>" just
    like a permanent scenario, and its id is folded into
    current_context["scenarios"] so downstream tools (e.g.
    summary_generation) pick it up without any further changes.
    """
    from app.tools.backend_tools import get_data_from_context, get_temp_evaluation_data

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
            {"current_context": to_fetch, "tenant": state.tenant}
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
                    "tenant": state.tenant,
                    "creation_session": creation_session,
                    "evaluation_id": evaluation_id,
                }
            )
            scenario_id = cleaned["scenario_id"]
            cache[f"scenarios {scenario_id}"] = {**cleaned, "evaluation_data": cleaned}
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


def execute_get_data_from_link(
    state: AgentState,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute get_data_from_link tool."""
    from app.tools.other_tools import get_data_from_link

    logger.info(f"Executing get_data_from_link for {url}")
    result = get_data_from_link.invoke(
        {
            "url": url,
            "headers": headers,
            "params": params,
        }
    )
    return result


def execute_get_base_scenario(
    state: AgentState,
    **kwargs,
) -> Dict[str, Any]:
    """Execute get_base_scenario tool."""
    from app.tools.backend_tools import get_base_scenario

    logger.info("Executing get_base_scenario tool")
    result = get_base_scenario.invoke({"tenant": state.tenant})
    return result


def execute_get_configuration_parameters(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute get_configuration_parameters tool.

    Fetches the backend's /widgets payload and flattens each entry down to
    the fields relevant for tuning a scenario: id, name, description, a
    single representative current value (the constant's "v", or the "loc"
    of a distribution when there's no single constant), and the allowed
    range/step.
    """
    from app.tools.backend_tools import get_widgets

    logger.info("Executing get_configuration_parameters tool")

    raw = get_widgets.invoke({"tenant": state.tenant})
    widgets = raw.get("widgets", raw) if isinstance(raw, dict) else raw

    cleaned = {
        group: [
            {
                "index_id": param["index_id"],
                "index_name": param["index_name"],
                "description": param.get("description"),
                "group": param.get("group", group),
                # "editable": param.get("editable", True),
                "current_value": param.get("v")
                or [param.get("loc"), param.get("scale")],
                "unit": param.get("index_category"),
                "min": param.get("min"),
                "max": param.get("max"),
                "step": param.get("step"),
            }
            for param in params
        ]
        for group, params in widgets.items()
    }

    return {"widgets": cleaned}


def execute_analyze_scenario_results(
    state: AgentState, query: str, **kwargs
) -> Dict[str, Any]:
    """Execute analyze_scenario_results tool."""

    logger.info(f"Executing analyze_scenario_results tool with query: {query}")

    _ensure_data_cached(state, state.cognitive.current_context)
    answer = analyze_scenario(state, query)
    return {"success": True, "message": answer}


def _make_widget_result(
    response: str, widget_name: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    action = {
        "type": "SHOW_WIDGET",
        "payload": {"widgetName": widget_name, "data": payload},
    }
    return {"success": True, "response": response, "assistant_action_data": [action]}


def _resolve_comparison_scenario_ids(
    state: AgentState, scenario_ids: list | None
) -> list:
    """Resolve the two scenario_ids to compare.

    Mirrors the fallback used elsewhere (see execute_summary_generation):
    if the reasoner didn't pass scenario_ids explicitly, fall back to the
    scenarios already resolved in current_context by get_context_ids. Also
    makes sure their evaluation data is actually cached before the caller
    tries to read sustainability_by_constraint off of it.
    """
    scenario_ids = scenario_ids or state.cognitive.current_context.get("scenarios", [])
    if not scenario_ids or len(scenario_ids) < 2:
        raise ValueError(
            "Two scenario_ids are required for a comparison — none (or only "
            "one) were provided and none are resolved in current_context. "
            "Call get_context_ids first to resolve the two scenarios to compare."
        )

    left_id, right_id = scenario_ids[0], scenario_ids[1]
    _ensure_data_cached(state, {"scenarios": [left_id, right_id]})
    return [left_id, right_id]


def _scenario_label(state: AgentState, scenario_id: str) -> str:
    cache = state.cognitive.context_cache
    return cache.get(f"scenarios {scenario_id}", {}).get("name", scenario_id)


def execute_comparison_plot(
    state: AgentState,
    scenario_ids: list | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Build the histogram comparison widget using backend data or safe mocks."""
    logger.info("Executing comparison_plot tool")

    try:
        left_id, right_id = _resolve_comparison_scenario_ids(state, scenario_ids)
        kpis_main = _parse_kpis(state, left_id)
        kpis_compare = _parse_kpis(state, right_id)
    except ValueError:
        kpis_main = kpis_compare = {}
        left_id = right_id = None

    if not kpis_main and not kpis_compare:
        return None

    data = {
        "labelLeft": _scenario_label(state, left_id),
        "labelRight": _scenario_label(state, right_id),
        "dataLeft": kpis_main,
        "dataRight": kpis_compare,
    }

    return _make_widget_result(
        "Ecco il confronto tra gli scenari:",
        "histogramComparison",
        {"payload": {"loading": False, **data}},
    )


def execute_kpi_comparison(
    state: AgentState,
    scenario_ids: list | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Build the KPI comparison widget using backend data or safe mocks."""
    logger.info("Executing kpi_comparison tool")

    left_id, right_id = _resolve_comparison_scenario_ids(state, scenario_ids)

    kpis_main = _parse_kpis(state, left_id)
    kpis_compare = _parse_kpis(state, right_id)
    if not kpis_main and not kpis_compare:
        return None

    comparison = {
        "kpisMain": kpis_main,
        "kpisCompare": kpis_compare,
    }
    return _make_widget_result(
        "Here are the KPI for the two scenarios",
        "indexComparison",
        comparison,
    )


def execute_show_load_plot(
    state: AgentState, payload: Dict[str, Any] | None = None, **kwargs
) -> Dict[str, Any]:
    """Build a load plot widget using backend data or safe mocks."""
    logger.info("Executing show_load_plot tool")
    data = payload or {
        "type": "load",
        "subsystem": "default",
        "data": {
            "curves": [],
            "points": [
                {
                    "name": "Presenze",
                    "x": [0, 1, 2, 3],
                    "y": [100, 200, 400, 800],
                    "customdata": [10, 20, 50, 95],
                    "marker": {"color": [0.1, 0.2, 0.5, 0.95], "size": 8},
                    "mode": "markers",
                    "type": "scatter",
                }
            ],
            "kpis": {
                "uncertainty": [
                    {
                        "usage": 100,
                        "usage_uncertainty": 0.1,
                        "tourists": 100,
                        "excursionists": 50,
                        "index": 0.1,
                    },
                    {
                        "usage": 200,
                        "usage_uncertainty": 0.2,
                        "tourists": 150,
                        "excursionists": 80,
                        "index": 0.2,
                    },
                    {
                        "usage": 400,
                        "usage_uncertainty": 0.5,
                        "tourists": 200,
                        "excursionists": 150,
                        "index": 0.5,
                    },
                    {
                        "usage": 800,
                        "usage_uncertainty": 0.95,
                        "tourists": 400,
                        "excursionists": 300,
                        "index": 0.95,
                    },
                ]
            },
            "capacity_mean": 500,
            "xMax": 4,
            "yMax": 1000,
        },
    }
    return _make_widget_result(
        "Ecco il grafico del carico turistico:",
        "plot",
        {
            "payload": {
                "type": "load",
                "subsystem": "default",
                "data": data.get("data", data),
                "loading": False,
            }
        },
    )


def execute_show_capacity_plot(
    state: AgentState, payload: Dict[str, Any] | None = None, **kwargs
) -> Dict[str, Any]:
    """Build a capacity (sustainability) plot widget using backend data or mock."""
    logger.info("Executing show_capacity_plot tool")
    data = payload or {
        "type": "capacity",
        "subsystem": "default",
        "data": {
            "curves": [
                {
                    "name": "Capacità spiagge",
                    "x": [0, 500, 1000, 1500],
                    "y": [2000, 1500, 500, 0],
                    "color": "rgb(180,4,38)",
                    "dash": "dash",
                }
            ],
            "points": [
                {
                    "name": "Attuale",
                    "x": [400],
                    "y": [800],
                    "color": "red",
                    "marker": {"size": 10, "color": "blue"},
                }
            ],
            "xMax": 2000,
            "yMax": 2500,
        },
    }
    return _make_widget_result(
        "Ecco il grafico di sostenibilità:",
        "plot",
        {
            "payload": {
                "type": "capacity",
                "subsystem": "default",
                "data": data.get("data", data),
                "loading": False,
            }
        },
    )


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


# =============================================================================
# CREATION STUBS
# =============================================================================


def execute_create_new_problem(
    state: AgentState,
    name: str,
    description: str,
    objective: str | None = None,
    additional_data: str | None = None,
) -> Dict[str, Any]:

    from app.tools.backend_tools import create_new_problem

    result = create_new_problem.invoke(
        {
            "tenant": state.tenant,
            "name": name,
            "description": description,
            "objective": objective,
            "additional_data": additional_data,
        }
    )

    return result


def execute_create_new_proposal(
    state: AgentState,
    name: str = "",
    problem_id: str = "",
    description: str = "",
    resources: str = "",
    context: str = "",
    impact: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import create_new_proposal

    result = create_new_proposal.invoke(
        {
            "tenant": state.tenant,
            "name": name,
            "problem_id": problem_id,
            "description": description,
            "resources": resources,
            "context": context,
            "impact": impact,
        }
    )

    return result


def _normalize_widget_overrides(state: AgentState, values: dict) -> dict:
    """Shape each override in `values` to match its widget's underlying
    representation before it's sent to the backend.

    Widgets come in two flavors (see execute_get_configuration_parameters):
      - constant widgets, keyed by "v" — a plain scalar. The override passed
        in `values` is already correct as-is; nothing to do.
      - distribution widgets, keyed by "loc"/"scale" — the backend expects a
        [loc, scale] pair, not a bare scalar. Two cases:
          * the caller already supplied both numbers (a 2-item list/tuple)
            -> use them directly as [new_loc, new_scale].
          * the caller supplied a single number -> that's treated as the
            new scale, and the widget's original loc is kept unchanged:
            [param.get("loc"), new_scale].

    Widgets not found in the catalog (e.g. an id typo) are passed through
    unchanged rather than dropped, so the backend can surface the real
    error instead of this silently discarding the override.
    """
    from app.tools.backend_tools import get_widgets

    raw = get_widgets.invoke({"tenant": state.tenant})
    widgets = raw.get("widgets", raw) if isinstance(raw, dict) else raw
    by_id = {
        param["index_id"]: param for params in widgets.values() for param in params
    }

    normalized = {}
    for index_id, value in values.items():
        param = by_id.get(index_id)

        if not param or param.get("v") is not None:
            # "v"-type (or unknown id): pass through unchanged.
            normalized[index_id] = value
            continue

        # "loc"/"scale"-type.
        if isinstance(value, (list, tuple)) and len(value) == 2:
            normalized[index_id] = [value[0], value[1]]
        else:
            normalized[index_id] = [param.get("loc"), value]

    return normalized


def execute_create_new_temp_scenario(
    state: AgentState,
    values: dict,
    base_scenario_id: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Create a temporary scenario from the given overrides and evaluate it.

    Stashes the result on state.cognitive.pending_temp_scenario so a later
    create_new_scenario call (in this or a following turn) can promote it.
    """
    from app.tools.backend_tools import (
        create_temp_scenario,
        get_base_scenario,
        create_cration_session,
    )

    if not values:
        raise ValueError(
            "'values' must contain at least one parameter override "
            "(index_id -> new numeric value)"
        )

    values = _normalize_widget_overrides(state, values)

    logger.info(
        f"Creating temp scenario on base '{base_scenario_id}' with values: {values}"
    )

    if not base_scenario_id:
        base_scenario_id = get_base_scenario.invoke({"tenant": state.tenant})

    # Create a new creation session if needed
    pending = state.cognitive.pending_temp_scenario or {}
    creation_session = (
        state.integrated_context.get("creation_session")
        or pending.get("creation_session")
        or None
    )
    if creation_session is None:
        creation_session = create_cration_session.invoke(state.tenant)

    logger.info(
        f"Retrieved required info: base_scenario id {base_scenario_id} and creation_session {creation_session}"
    )

    scenario_result = create_temp_scenario.invoke(
        {
            "tenant": state.tenant,
            "values": values,
            "base_scenario_id": base_scenario_id,
            "creation_session": creation_session,
        }
    )

    scenario_id = scenario_result["scenario_id"]
    evaluation_id = scenario_result["evaluation_id"]
    creation_session = scenario_result.get("creation_session", creation_session)
    evaluation = scenario_result["data"]

    # Remember this so create_new_scenario can promote it without redoing
    # the simulation, and so the next what-if preview this session can
    # reuse the same creation_session.
    state.cognitive.pending_temp_scenario = {
        "scenario_id": scenario_id,
        "evaluation_id": evaluation_id,
        "base_scenario_id": base_scenario_id,
        "creation_session": creation_session,
        "values": values,
    }

    return {
        "scenario_id": scenario_id,
        "evaluation_id": evaluation_id,
        "base_scenario_id": base_scenario_id,
        "values": values,
        "temporary": True,
        "evaluation": evaluation,
    }


def execute_create_new_scenario(
    state: AgentState,
    name: str = "",
    description: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Promote the pending temporary scenario (created and evaluated by
    create_new_temp_scenario) to a permanent, named scenario."""
    from app.tools.backend_tools import promote_scenario

    pending = state.cognitive.pending_temp_scenario
    if not pending:
        raise ValueError(
            "No temporary scenario available to save. Call create_new_temp_scenario "
            "first to preview the desired values, then create_new_scenario to save it."
        )

    logger.info(
        f"Promoting temp scenario '{pending['scenario_id']}' to permanent as '{name}'"
    )

    result = promote_scenario.invoke(
        {
            "tenant": state.tenant,
            "creation_session": pending["creation_session"],
            "scenario_id": pending["scenario_id"],
            "name": name,
            "description": description,
        }
    )

    # Consumed — clear it so a later create_new_scenario without a fresh
    # preview fails loudly instead of accidentally re-saving the same one.
    state.cognitive.pending_temp_scenario = None

    return result


# =============================================================================
# EDIT STUBS
# =============================================================================


def execute_edit_problem(
    state: AgentState,
    problem_id: str = "",
    name: str = "",
    description: str = "",
    objective: str | None = None,
    additional_data: str | None = None,
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import edit_problem

    result = edit_problem.invoke(
        {
            "tenant": state.tenant,
            "problem_id": problem_id,
            "name": name,
            "description": description,
            "objective": objective,
            "additional_data": additional_data,
        }
    )

    return result


def execute_edit_proposal(
    state: AgentState,
    proposal_id: str = "",
    name: str = "",
    problem_id: str = "",
    description: str = "",
    resources: str = "",
    context: str = "",
    impact: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import edit_proposal

    result = edit_proposal.invoke(
        {
            "tenant": state.tenant,
            "proposal_id": proposal_id,
            "name": name,
            "problem_id": problem_id,
            "description": description,
            "resources": resources,
            "context": context,
            "impact": impact,
        }
    )

    return result


def execute_edit_scenario(
    state: AgentState,
    scenario_id: str = "",
    name: str = "",
    description: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Stub executor for edit_scenario — feature not yet implemented."""

    from app.tools.backend_tools import edit_scenario

    result = edit_scenario.invoke(
        {
            "tenant": state.tenant,
            "scenario_id": scenario_id,
            "name": name,
            "description": description,
        }
    )

    return result


# =============================================================================
# DELETE STUBS
# =============================================================================


def execute_delete_problem(
    state: AgentState,
    problem_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import delete_problem

    result = delete_problem.invoke({"problem_id": problem_id, "tenant": state.tenant})

    return result


def execute_delete_proposal(
    state: AgentState,
    proposal_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import delete_proposal

    result = delete_proposal.invoke(
        {"proposal_id": proposal_id, "tenant": state.tenant}
    )

    return result


def execute_delete_scenario(
    state: AgentState,
    scenario_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import delete_scenario

    result = delete_scenario.invoke(
        {"scenario_id": scenario_id, "tenant": state.tenant}
    )

    return result


# =============================================================================
# GLOSSARY LOOKUP
# =============================================================================


def execute_lookup_glossary(
    state: AgentState,
    query: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute lookup_glossary tool.

    Performs a case-insensitive fuzzy search over the GLOSSARY dict in config.
    Matches the query tokens against: term name, aliases, and related_terms.
    Returns all matching entries with their full detail.
    """
    from app.utils.terminology import GLOSSARY

    logger.info(f"Executing lookup_glossary | query='{query}'")

    tokens = [t.strip().lower() for t in query.split() if t.strip()]
    if not tokens:
        return {
            "success": False,
            "error": "Empty query — please provide at least one search term.",
            "matches": [],
        }

    matches = {}
    for entry in GLOSSARY:
        term = entry["term"]
        # Build a flat list of strings to match against. "it" is included
        # here (unlike in app.utils.terminology's text-matcher) because this
        # tool is meant to resolve a user's query — including one phrased in
        # Italian — back to the right entry, not to decide what to generate.
        searchable = (
            [term]
            + entry.get("aliases", [])
            + entry.get("related_terms", [])
            + entry.get("it", [])
        )
        searchable_lower = " ".join(s.lower() for s in searchable)

        if any(tok in searchable_lower for tok in tokens):
            matches[term] = entry

    if not matches:
        return {
            "success": True,
            "message": (
                f"No glossary entries found for '{query}'. "
                "Try broader keywords or ask about a specific platform concept."
            ),
            "matches": [],
        }

    # Format for readability in the output generator
    formatted = []
    for term, entry in matches.items():
        formatted.append(
            {
                "term": term,
                "definition": entry["definition"],
                "aliases": entry.get("aliases", []),
                "related_terms": entry.get("related_terms", []),
                "examples": entry.get("examples", []),
                "it": entry.get("it", []),
            }
        )

    logger.info(f"lookup_glossary found {len(formatted)} match(es) for '{query}'")

    return {
        "success": True,
        "query": query,
        "matches": formatted,
    }
