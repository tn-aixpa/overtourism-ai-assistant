import pytest
from app.agent.state import AgentState

@pytest.fixture
def empty_state():

    return AgentState(
        messages=[],
        next_action=None,
        response="",
        session_id="",
        problem_id="",
        scenario_ids=None, 
        data=None,
        data_loaded_at=None,
        selected_roles=None,
        expert_answers=None,
        problem_info=None,
        extracted_problem_info={},
        extracted_all_problem=False,
        required_scenario_info=None,
        extracted_scenarios=None,
        validated_scenarios=None,
        scenario_preferences=None,
        scenario_strategy=None,
        scenario_candidates=None,
        prepared_scenarios=None,
        scenario_results=None,
        current_input=None,
        awaiting_confirmation=None,
        running_scenario=False
    )
            