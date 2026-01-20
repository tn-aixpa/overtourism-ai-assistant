import pytest
from app.agent.state import AgentState

@pytest.fixture
def empty_state():
    return AgentState(
        user_message="",
        next_action=None,
        response="",
        problem_id="",
        scenario_ids=None,
        data=None,
        data_loaded_at=None,
        current_input={},
        awaiting_confirmation=False,
        running_simulation=False,
        selected_roles=["Data Analyst"],
        expert_answers={},
    )