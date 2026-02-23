import pytest
from app.agent.state import AgentState, CognitiveState


@pytest.fixture
def empty_state():

    return AgentState(
        # Interface layer
        conversation=[],

        # Orchestration Layer
        session_id="",
        last_user_en=None,
        user_lang="it",

        # Cognitive Layer
        cognitive=CognitiveState(
            next_action=None,

            # Problem context
            problem_id="",
            problem_info_to_extract={},
            extracted_problem_info={},
            extracted_all_problem=False,

            # Scenario context
            scenario_ids=[],
            scenario_info_to_extract={},
            extracted_all_scenario=False,
            scenarios_to_generate=[],
            validation_errors="",

            # Expert reasoning
            selected_roles=[],
            expert_answers={},

            # Data layer
            data={},
            editable_indexes={}
        )
    )