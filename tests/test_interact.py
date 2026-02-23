import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.nodes.iteraction import interact_scenario
from app.utils.data import parse_data
from app.agent.state import ConversationMessage

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
    
    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = [id]
    state.cognitive.next_action = "INTERACT_SCENARIO"
    state.cognitive.selected_roles = ["Data Analyst"]

    with open(f"tests/data/{file_name}", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message
    state = interact_scenario(state)

    response = state.conversation[-1].content if state.conversation and state.conversation[-1].role == "assistant" else ""
    assert check in response
