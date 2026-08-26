"""Scenario tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolCategory
from app.utils.backend_entities_parameters import (
    SCENARIO_PARAMETERS,
    TEMP_SCENARIO_PARAMETERS,
)


def create_list_available_scenarios_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_available_scenarios",
        description="List all available scenarios from the backend",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description="Fetches and displays all scenarios.",
        parameters=[],
        output_description="Dictionary containing all IDs, names, and relationships",
        tags=["data", "read-only", "navigation"],
    )


def create_get_base_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_base_scenario",
        description="Retrieve the base scenario ID from the backend.",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetch the ID of the base scenario from the backend, using the same backend tool as the platform's get_base_scenario helper."
        ),
        parameters=[],
        output_description="The base scenario ID",
        tags=["data", "read-only", "scenario", "base"],
    )


def create_new_temp_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_temp_scenario",
        description=(
            "Create a temporary, unsaved scenario with modified parameter values and evaluate it"
        ),
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Applies the given parameter overrides on top of a base scenario, creates a "
            "throwaway (temporary) scenario from them, and immediately evaluates it. Use this "
            "to preview the effect of a what-if change (e.g. 'what if I double the parking "
            "turnover?') before deciding whether to save it as a real scenario. If the user "
            "expresses the change in relative terms ('double', 'increase by 20%', ...), first "
            "call get_configuration_parameters to resolve the parameter's current value and "
            "compute the final numeric value yourself, then pass the resulting index_id -> "
            "value mapping here. This tool does not require user confirmation and does not "
            "persist anything permanently — nothing is saved until create_new_scenario is "
            "called afterwards on the scenario it produced."
        ),
        parameters=TEMP_SCENARIO_PARAMETERS,
        output_description=(
            "The temporary scenario_id, its evaluation_id, and the evaluation results "
            "(sustainability index and per-constraint breakdown)."
        ),
        tags=["scenario", "simulation", "preview"],
    )


def create_new_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="create_new_scenario",
        description="Save a previously previewed temporary scenario as a permanent scenario",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description=(
            "Persists the temporary scenario that create_new_temp_scenario already created "
            "and evaluated, giving it a permanent name and description. "
            "create_new_temp_scenario MUST have been called earlier in the conversation — a "
            "scenario and its evaluation must already exist before it can be saved. If no "
            "temporary scenario is available yet, ask the user what values they want to "
            "simulate and call create_new_temp_scenario first, let them review the results, "
            "and only call this tool once they confirm they want to keep it. Optionally, the "
            "scenario can be linked to a proposal via proposal_id — only set this if the user "
            "mentions or clearly implies an associated proposal; never ask for one otherwise."
        ),
        parameters=SCENARIO_PARAMETERS,
        output_description="Acknowledgement of successful save with the final scenario_id.",
        tags=["write", "scenario"],
    )


def edit_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="edit_scenario",
        description="Edit an available scenario",
        category=ToolCategory.SCENARIO_MANAGEMENT,
        long_description="Modify one or more attributes of a scenario that was already defined",
        parameters=SCENARIO_PARAMETERS,
        output_description="Acknowledgement of successful edit or request for more details",
        tags=["write", "scenario"],
    )


def delete_scenario_tool() -> ToolDefinition:
    return ToolDefinition(
        name="delete_scenario",
        description="Delete a scenario",
        category=ToolCategory.PROPOSAL_MANAGEMENT,
        long_description="Delete a Scenario in the platform.",
        parameters=[],
        output_description="Acknowledgement of successful deletetion or request for more details",
        tags=["write", "proposal"],
    )


__all__ = [
    "create_list_available_scenarios_tool",
    "create_get_base_scenario_tool",
    "create_new_temp_scenario_tool",
    "create_new_scenario_tool",
    "edit_scenario_tool",
    "delete_scenario_tool",
]
