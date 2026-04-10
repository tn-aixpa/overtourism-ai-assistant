ALLOWED_ROLES = {
    "Data Analyst": "has knowledge of numerical or structured scenario data.",
    "Environment Specialist": "can reason about environmental impacts and sustainability.",
    "Urban Planner": "can reason about infrastructure, mobility, and land-use tradeoffs.",
}

DRAW_CONVERSATION = True

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 5

SYSTEM_DESCRIPTION = """
The system is able to access problems, proposals and scenarios connected to overtourism and mobility problems.
Different operations are allowed depending on the active context:
- No active context: you can 1) ask questions to explore the available data, but you cannot interact with it; 2) create new problems.
- With active problems you can interact with the problem or create new proposals.
- With active proposals you can interact with the proposal or create new scenarios.
- With active scenarios you can explore results, decide to compare it another scenario.
"""

BASE_SCENARIO_ID = "model_0" #TODO place it somewhere else
BACKEND_URL = "http://0.0.0.0:8000/api/v1/"