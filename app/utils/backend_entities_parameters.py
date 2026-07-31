from app.tools.tool_schema import ToolParameter

# ---------------------------------------------------------------------------
# Shared parameter definitions.
#
# Several create_* / edit_* tool pairs (and edit-only variants) take
# effectively the same parameters. Rather than redefining each ToolParameter
# twice (and risking them drifting apart), we define them once here and reuse
# the same instances across tools.
#
# Where the original create_* and edit_* versions of a parameter had
# different descriptions, one was picked arbitrarily below (marked with a
# comment) — feel free to adjust the wording.
# ---------------------------------------------------------------------------

# --- Problem parameters -----------------------------------------------------
PROBLEM_NAME_PARAM = ToolParameter(
    name="name",
    description="Short name or title for the new problem.",
    type="string",
    required=True,
)
PROBLEM_DESCRIPTION_PARAM = ToolParameter(
    name="description",
    description="Detailed description of the problem to be addressed.",
    type="string",
    required=True,
)
PROBLEM_OBJECTIVE_PARAM = ToolParameter(
    name="objective",
    description="The objectives we want to achieve when addressing the problem.",
    type="string",
    required=False,
)
# create_new_problem_tool called this "additional_data", edit_problem_tool called
# it "links" with a different description. Arbitrarily standardized on "links"
# with edit_problem_tool's description.
PROBLEM_LINKS_PARAM = ToolParameter(
    name="links",
    description="Additional data or piece of information useful to understand the problem.",
    type="string",
    required=False,
)

# TODO: add groups, extra?

PROBLEM_PARAMETERS = [
    PROBLEM_NAME_PARAM,
    PROBLEM_DESCRIPTION_PARAM,
    PROBLEM_OBJECTIVE_PARAM,
    PROBLEM_LINKS_PARAM,
]

# --- Proposal parameters -----------------------------------------------------
PROPOSAL_NAME_PARAM = ToolParameter(
    name="name",
    description="Short name or title for the new proposal.",
    type="string",
    required=True,
)
PROPOSAL_PROBLEM_ID_PARAM = ToolParameter(
    name="problem_id",
    description="Problem that this proposal addresses.",
    type="string",
    required=True,
)
PROPOSAL_DESCRIPTION_PARAM = ToolParameter(
    name="description",
    description="Detailed description of the proposed strategy.",
    type="string",
    required=True,
)
PROPOSAL_RESOURCES_PARAM = ToolParameter(
    name="resources",
    description="Links or references to documents, datasets or support material",
    type="string",
    required=False,
)
PROPOSAL_CONTEXT_PARAM = ToolParameter(
    name="context",
    description=(
        "Factors or elements that might impact the proposed solution "
        "(e.g. seasonality, weather conditions, events, etc.)"
    ),
    type="string",
    required=False,
)
PROPOSAL_IMPACT_PARAM = ToolParameter(
    name="impact",
    description=(
        "Expected impact of the proposal (e.g on the environment, economical "
        "return, ...). Possibly specify also the related indicators or metrics "
        "(e.g. reduce by 20% the air pollution)."
    ),
    type="string",
    required=False,
)

# TODO: add status  (draft / submitted / accepted / rejected), extra?, related_scenario_ids

PROPOSAL_PARAMETERS = [
    PROPOSAL_NAME_PARAM,
    PROPOSAL_PROBLEM_ID_PARAM,
    PROPOSAL_DESCRIPTION_PARAM,
    PROPOSAL_RESOURCES_PARAM,
    PROPOSAL_CONTEXT_PARAM,
    PROPOSAL_IMPACT_PARAM,
]

# --- Scenario parameters -----------------------------------------------------
SCENARIO_NAME_PARAM = ToolParameter(
    name="name",
    description="Short name or title for the new scenario.",
    type="string",
    required=True,
)
SCENARIO_DESCRIPTION_PARAM = ToolParameter(
    name="description",
    description="Description of the parameter configuration to simulate.",
    type="string",
    required=True,
)

# NOTE: base_scenario_id / values / extras are deliberately NOT parameters of
# create_new_scenario. They are supplied earlier, to create_new_temp_scenario,
# which creates and evaluates the (unsaved) scenario first; create_new_scenario
# only ever promotes that already-evaluated temp scenario to permanent, so it
# just needs the final name/description.
SCENARIO_PARAMETERS = [
    SCENARIO_NAME_PARAM,
    SCENARIO_DESCRIPTION_PARAM,
]

# --- Temp scenario parameters -------------------------------------------
SCENARIO_VALUES_PARAM = ToolParameter(
    name="values",
    description=(
        "Mapping of configuration parameter index_id to its new numeric value, e.g. "
        '{"excursionists_per_vehicle_average": 3.4, "excursionists_parking_turnover": 2.4}. '
        "Only include the parameters the user actually wants to change; every key must be "
        "an index_id returned by get_configuration_parameters. For relative changes "
        "expressed in words (e.g. 'double the parking turnover', 'increase X by 20%'), "
        "first fetch the current value with get_configuration_parameters and compute the "
        "final numeric value yourself before calling this tool."
    ),
    type="object",
    required=True,
    schema={"additionalProperties": {"type": "number"}},
)


TEMP_SCENARIO_PARAMETERS = [
    SCENARIO_VALUES_PARAM,
]
