import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.nodes.iteraction import compare_scenarios
from app.utils.data import parse_data
from app.agent.state import ConversationMessage

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

def test_compare(empty_state, problem_id, file_name1, id1, file_name2, id2, message, check):

    state = replace(empty_state)
    
    state.cognitive.problem_id = problem_id
    state.cognitive.scenario_ids = [id1, id2]
    state.cognitive.next_action = "COMPARE_SCENARIOS"
    state.cognitive.selected_roles = ["Data Analyst"]

    state.cognitive.data = {}
    with open(f"tests/data/{file_name1}", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/{file_name2}", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message
    state = compare_scenarios(state)

    correct = False
    response = state.conversation[-1].content if state.conversation[-1].role == "assistant" else ""
    if any(string in response.lower() for string in check):
        correct = True
        
    assert correct
