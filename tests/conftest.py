import pytest
from state import AgentState

@pytest.fixture
def empty_state():
    return AgentState(
        user_message="",
        simulation_id=None,
        sim1=None,
        sim2=None,
        pending_inputs={},
        missing_inputs=[],
        awaiting_confirmation=False,
        running_simulation=False,
        next_action=None,
        response="",
    )
