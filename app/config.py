ALLOWED_ROLES = {
    "Data Analyst": "has knowledge of numerical or structured scenario data.",
    "Environment Specialist": "can reason about environmental impacts and sustainability.",
    "Urban Planner": "can reason about infrastructure, mobility, and land-use tradeoffs.",
}

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 5

SYSTEM_DESCRIPTION = """
# General description
The system supports analysis and decision-making for overtourism and mobility problems,
through a structured hierarchy of Problems, Proposals, and Scenarios.

# Core concepts

- **Problem**: a critical situation or phenomenon to be analyzed or managed (e.g., overtourism,
  extreme events, unregistered tourism), which requires data- and model-based decision support.
- **Proposal**: a possible strategy to address a problem. A proposal may include multiple scenarios,
  each exploring different parameter configurations.
- **Scenario**: a simulation that explores the consequences of changes in a model's parameters,
  useful for evaluating and comparing alternative strategies.

# Context levels and allowed operations

The system operates on an active context, which determines what operations and tools are available.
Always set the appropriate context before performing context-dependent operations.

## No active context
Available tools: get_system_capabilities, list_problems, get_context_details,
set_active_context, extract_problem_details, create_problem

## Problem context (active problem set)
Available tools: get_system_capabilities, list_problems, get_context_details,
set_active_context, extract_problem_details, create_problem,
extract_proposal_details, create_proposal, interact_with_context

## Proposal context (active proposal set)
Available tools: get_system_capabilities, list_problems, get_context_details,
set_active_context, extract_problem_details, create_problem,
extract_scenario_details, create_scenario

## Scenario context (active scenario set)
To be defined.

# Typical workflows

1. **Explore**: call list_problems → set_active_context → interact_with_context
2. **Create a proposal**: set a problem context → extract_proposal_details → confirm → create_proposal
3. **Create a scenario**: set a proposal context → extract_scenario_details → confirm → create_scenario

# Important rules

- extract_* tools always require user confirmation before the corresponding create_* tool is called.
- Proposals require an active problem context; scenarios require an active proposal context.
- set_active_context and get_context_details are always available regardless of current context.
"""

BASE_SCENARIO_ID = "scenario_base" #TODO place it somewhere else
BACKEND_URL = "http://0.0.0.0:8000/api/v2/"

VERBOSE = False