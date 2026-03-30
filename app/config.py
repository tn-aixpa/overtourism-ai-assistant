ALLOWED_ROLES = {
    "Data Analyst": "has knowledge of numerical or structured scenario data.",
    "Environment Specialist": "can reason about environmental impacts and sustainability.",
    "Urban Planner": "can reason about infrastructure, mobility, and land-use tradeoffs.",
}

DRAW_CONVERSATION = True

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 5

ALLOWED_OPERATIONS = """
- With active problems you can interact, manage or create new proposals.
- With active proposals you can interact, manage or create new scenarios.
- With active scenarios you can explore results, decide to compare it another scenario, run new simulation modifying parameters.
"""