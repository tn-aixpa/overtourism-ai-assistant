import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.nodes.compare import compare_simulations

@pytest.mark.parametrize(
    "file_name1, file_name2, message, check",
    [
        ("validation-overtourism-002-scenario-base-short.json",
         "validation-overtourism-002-scenario-1_short.json",
         "Did overturism improve in the scenario-1 compared to base?",
         ["yes", "decreased", "improved"]),
    ],
)

def test_interact(empty_state, file_name1, file_name2, message, check):

    state = replace(empty_state)
    
    state.sim1_id = file_name1
    state.sim2_id = file_name2
    state.simulation_data_loaded_at = datetime.now()
    state.next_action = "INTERACT_SIMULATION"
    state.role = "Data Analyst"

    state.simulation_data = {}
    with open(f"tests/data/{file_name1}", "r") as f:
        state.simulation_data[file_name1] = json.loads(f.read())
    with open(f"tests/data/{file_name2}", "r") as f:
        state.simulation_data[file_name2] = json.loads(f.read())

    state.user_message = message
    state = compare_simulations(state)

    correct = False
    if any(string in state.response.lower() for string in check):
        correct = True
    
    assert correct
