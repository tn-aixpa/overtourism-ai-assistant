import pytest
from app.agent.state import AgentState

@pytest.fixture
def empty_state():

    return AgentState(
        messages=[],
        next_action=None,
        error_message="",
        session_id="",
        problem_id="",
        scenario_ids=None, 
        data=None,
        data_loaded_at=None,
        editable_idexes={},
        selected_roles=None,
        expert_answers=None,
        problem_info_to_extract=None,
        extracted_problem_info={},
        extracted_all_problem=False,
        scenario_info_to_extract=None,
        scenarios_to_generate=None,
        extracted_all_scenario=False,
        running_scenario=False
    )
            