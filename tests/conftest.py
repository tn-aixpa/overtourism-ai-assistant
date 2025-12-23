import pytest
from state import AgentState

@pytest.fixture
def empty_state():
    return AgentState(
        user_message="",
        simulation_id=None,
        simulation_data = None,
        simulation_data_loaded_at=None,
        interact_blocked_until=None,
        sim1=None,
        sim2=None,
        pending_inputs={},
        missing_inputs=[],
        awaiting_confirmation=False,
        running_simulation=False,
        next_action=None,
        response="",
    )
