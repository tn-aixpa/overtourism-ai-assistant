"""Scenario tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState
from app.utils.configuration_parameters import load_indexes, resolve_overrides

logger = logging.getLogger(__name__)


def execute_get_base_scenario(
    state: AgentState,
    **kwargs,
) -> Dict[str, Any]:
    """Execute get_base_scenario tool."""
    from app.tools.executor_backend_tools import get_base_scenario

    logger.info("Executing get_base_scenario tool")
    result = get_base_scenario.invoke({"territory": state.territory})
    return result


def execute_create_new_temp_scenario(
    state: AgentState,
    values: dict,
    base_scenario_id: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Create a temporary scenario from the requested parameter changes and
    evaluate it.

    ``values`` maps a parameter name to a new value whose shape depends on the
    parameter's kind (number / choice / [low, high] range) or to a relative
    operation — see app.utils.configuration_parameters. Everything is
    validated against the backend's /configuration first; if any value is not
    acceptable nothing is created and the result carries ``created: False``
    plus the list of problems (returned as a normal observation, not raised,
    so the reasoner can fix the call or ask the user instead of the turn
    ending in the generic error path).

    On success, stashes the result on state.cognitive.pending_temp_scenario
    so a later create_new_scenario call (in this or a following turn) can
    promote it.
    """
    from app.tools.executor_backend_tools import (
        create_temp_scenario,
        get_base_scenario,
        create_cration_session,
        get_widgets,
    )

    if not isinstance(values, dict) or not values:
        raise ValueError(
            "'values' must contain at least one parameter change "
            "(parameter name -> new value)"
        )

    indexes = load_indexes(get_widgets.invoke({"territory": state.territory}))
    resolution = resolve_overrides(indexes, values)

    if resolution["problems"] or not resolution["payload"]:
        logger.info(f"Temp scenario not created. Problems: {resolution['problems']}")
        rejected: Dict[str, Any] = {
            "created": False,
            "temporary": False,
            "problems": resolution["problems"],
            "requested_values": values,
        }
        if not resolution["problems"]:
            rejected["message"] = (
                "Every requested value equals the current one, so there is "
                "nothing different to evaluate."
            )
            rejected["changes"] = resolution["changes"]
        return rejected

    changes = resolution["changes"]
    values = resolution["payload"]

    logger.info(
        f"Creating temp scenario on base '{base_scenario_id}' with values: {values}"
    )

    if not base_scenario_id:
        base_scenario_id = get_base_scenario.invoke({"territory": state.territory})

    # Create a new creation session if needed
    pending = state.cognitive.pending_temp_scenario or {}
    creation_session = (
        state.integrated_context.get("creation_session")
        or pending.get("creation_session")
        or None
    )
    if creation_session is None:
        creation_session = create_cration_session.invoke(state.territory)

    logger.info(
        f"Retrieved required info: base_scenario id {base_scenario_id} and creation_session {creation_session}"
    )

    scenario_result = create_temp_scenario.invoke(
        {
            "territory": state.territory,
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
        # Human-readable "label: from → to" lines, used by the save
        # confirmation recap (see waiting._wait_instructions).
        "changes": changes,
    }

    return {
        "created": True,
        "scenario_id": scenario_id,
        "evaluation_id": evaluation_id,
        "base_scenario_id": base_scenario_id,
        "values": values,
        "applied_changes": changes,
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
            "territory": state.territory,
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
            "territory": state.territory,
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
        {"scenario_id": scenario_id, "territory": state.territory}
    )

    return result


EXECUTORS = {
    "get_base_scenario": execute_get_base_scenario,
    "create_new_temp_scenario": execute_create_new_temp_scenario,
    "create_new_scenario": execute_create_new_scenario,
    "edit_scenario": execute_edit_scenario,
    "delete_scenario": execute_delete_scenario,
}
