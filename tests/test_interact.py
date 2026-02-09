import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.nodes.interact import interact_scenario
from app.utils.data import parse_data

@pytest.mark.parametrize(
    "file_name, id,  message, check",
    [
        ("test_1.json",
         "model_3",
         "What is the most critical constraint?",
         "parking"),
        ("test_base.json",
         "model_0",
         "What is the most critical constraint?",
         "parking"),
    ],
)

def test_interact(empty_state, file_name, id, message, check):

    state = replace(empty_state)
    
    state.problem_id = "parcheggi_200"
    state.scenario_ids = [id]
    state.data_loaded_at = datetime.now()
    state.next_action = "INTERACT_SCENARIO"
    state.selected_roles = ["Data Analyst"]

    with open(f"tests/data/{file_name}", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.messages.append({"role": "user", "content": message})
    state = interact_scenario(state)

    assert check in state.response
