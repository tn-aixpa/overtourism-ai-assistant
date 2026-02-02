import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.nodes.compare import compare_scenarios
from app.utils.data import parse_data

@pytest.mark.parametrize(
    "problem_id, file_name1, id1, file_name2, id2, message, check",
    [
        ( "parcheggi_200",
         "test_base.json",
         "model_0",
         "test_1.json",
         "model_3",
         "Did overturism improve in the scenario-1 compared to base?",
         ["yes", "decreased", "improved"]),
    ],
)

def test_interact(empty_state, problem_id, file_name1, id1, file_name2, id2, message, check):

    state = replace(empty_state)
    
    state.problem_id = problem_id
    state.scenario_ids = [id1, id2]
    state.data_loaded_at = datetime.now()
    state.next_action = "INTERACT_SCENARIO"
    state.role = "Data Analyst"

    state.data = {}
    with open(f"tests/data/{file_name1}", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/{file_name2}", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.user_message = message
    state = compare_scenarios(state)

    correct = False
    if any(string in state.response.lower() for string in check):
        correct = True
        
    assert correct
