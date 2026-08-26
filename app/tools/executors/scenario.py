"""Scenario tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def execute_list_available_scenarios(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_scenarios tool."""
    from app.tools.executor_backend_tools import get_all_scenarios

    logger.info("Executing list_available_scenarios tool")
    result = get_all_scenarios.invoke({"tenant": state.tenant})

    return result


def execute_get_base_scenario(
    state: AgentState,
    **kwargs,
) -> Dict[str, Any]:
    """Execute get_base_scenario tool."""
    from app.tools.executor_backend_tools import get_base_scenario

    logger.info("Executing get_base_scenario tool")
    result = get_base_scenario.invoke({"tenant": state.tenant})
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
    from app.tools.executor_backend_tools import get_widgets

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
    from app.tools.executor_backend_tools import (
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
    proposal_id: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Promote the pending temporary scenario (created and evaluated by
    create_new_temp_scenario) to a permanent, named scenario."""
    from app.tools.executor_backend_tools import promote_scenario

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
            "proposal_id": proposal_id,
        }
    )

    # Consumed — clear it so a later create_new_scenario without a fresh
    # preview fails loudly instead of accidentally re-saving the same one.
    state.cognitive.pending_temp_scenario = None

    return result


def execute_edit_scenario(
    state: AgentState,
    scenario_id: str = "",
    name: str = "",
    description: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Stub executor for edit_scenario — feature not yet implemented."""

    from app.tools.executor_backend_tools import edit_scenario

    result = edit_scenario.invoke(
        {
            "tenant": state.tenant,
            "scenario_id": scenario_id,
            "name": name,
            "description": description,
        }
    )

    return result


def execute_delete_scenario(
    state: AgentState,
    scenario_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.executor_backend_tools import delete_scenario

    result = delete_scenario.invoke(
        {"scenario_id": scenario_id, "tenant": state.tenant}
    )

    return result


EXECUTORS = {
    "list_available_scenarios": execute_list_available_scenarios,
    "get_base_scenario": execute_get_base_scenario,
    "create_new_temp_scenario": execute_create_new_temp_scenario,
    "create_new_scenario": execute_create_new_scenario,
    "edit_scenario": execute_edit_scenario,
    "delete_scenario": execute_delete_scenario,
}
