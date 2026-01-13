import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.nodes.interact import interact_simulation

@pytest.mark.parametrize(
    "file_name, message, check",
    [
        ("validation-overtourism-002-scenario-1_short.json",
         "What is the most critical constraint?",
         "alberghi"),
        ("validation-overtourism-002-scenario-base-short.json",
         "What is the most critical constraint?",
         "parcheggi"),
    ],
)

def test_interact(empty_state, file_name, message, check):

    state = replace(empty_state)
    
    state.sim1_id = file_name
    state.simulation_data_loaded_at = datetime.now()
    state.next_action = "INTERACT_SIMULATION"
    state.role = "Data Analyst"

    with open(f"tests/data/{file_name}", "r") as f:
        state.simulation_data = json.loads(f.read())

    state.user_message = message
    state = interact_simulation(state)

    assert check in state.response
