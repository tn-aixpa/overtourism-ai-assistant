import pytest
from app.agent.state import AgentState

@pytest.fixture
def empty_state():
    return AgentState(
        user_message="",
        sim_ids=None,
        simulation_data=None,
        simulation_data_loaded_at=None,
        pending_inputs={},
        missing_inputs=[],
        awaiting_confirmation=False,
        running_simulation=False,
        selected_roles=["Data Analyst"],
        expert_answers={},
        next_action=None,
        response="",
    )