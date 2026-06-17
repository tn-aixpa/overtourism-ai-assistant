ALLOWED_ROLES = {
    "Data Analyst": "has knowledge of numerical or structured scenario data.",
    "Environment Specialist": "can reason about environmental impacts and sustainability.",
    "Urban Planner": "can reason about infrastructure, mobility, and land-use tradeoffs.",
}

DRAW_CONVERSATION = True

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 5

SYSTEM_DESCRIPTION = """
# General description
The system is able to access problems, proposals and scenarios connected to overtourism and mobility problems.

# Definitions

- Problem: a critical situation or phenomenon to be analyzed or managed (e.g., overtourism, extreme events, unregistered tourism), which requires data- and model-based decision support.
- Proposal: a possible stragety to solve or try to reduce the effects of a problem. The effect of the proposal might be reached in different ways, changing different parameters, for this reason a proposal might incldue different scenarios.
- Scenario: a simulation that explores the consequences of changes in a model's parameters, useful for evaluating alternative strategies.

# Allowed operations

Different operations are allowed depending on the active context.

- Operations allowed in any context: ask questions about the system, list available problems/proposals/scenarios, activate/deactivate context, create a new problem.
- With active problems you can interact with the problem or create new proposals.
- With active proposals you can interact with the proposal or create new scenarios.
- With active scenarios you can explore results, decide to compare it another scenario.
"""

BASE_SCENARIO_ID = "scenario_base" #TODO place it somewhere else
BACKEND_URL = "http://0.0.0.0:8000/api/v2/"

VERBOSE = False