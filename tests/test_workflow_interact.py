from dataclasses import replace
from datetime import datetime
import json

from app.agent.graph import app
from app.agent.state import ConversationMessage
from app.utils.data import parse_data
from app.config import DRAW_CONVERSATION
from app.utils.common import to_state

def test_full_workflow_invalid(empty_state):
    state = replace(empty_state)
    state.conversation.append(
        ConversationMessage(
            role="user",
            content="Tell me about the weather in Paris",
            timestamp=datetime.now()
    ))

    result_dict = app.invoke(state)
    result = to_state(result_dict)

    response = result.conversation[-1].content if result.conversation[-1].role == "assistant" else ""
    assert response == "I'm sorry, I can't answer this type of request."

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation, "logs/invalid.png")

def test_full_workflow_interact(empty_state):

    state = replace(empty_state)
    
    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = ["model_0"]

    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    message = "What is the most critical constraint and what does this imply?"
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message

    result_dict = app.invoke(state)
    result = to_state(result_dict)

    assert result.cognitive.next_action == "INTERACT_SCENARIO"
    assert len(result.cognitive.selected_roles) >= 1
    response = result.conversation[-1].content if result.conversation and result.conversation[-1].role == "assistant" else ""
    assert response != "" and "not able to handle this request" not in response and "parking" in response
    assert "parking" in response

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation, "logs/interact.png")
    
    
def test_full_workflow_compare(empty_state):
    state = replace(empty_state)

    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = ["model_0", "model_3"]

    state.cognitive.data = {}
    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/test_1.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    message="What changed between the two scenarios and what was the impact of the change?"
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message

    result_dict = app.invoke(state)
    result = to_state(result_dict)
    assert result.cognitive.next_action == "COMPARE_SCENARIOS"
    assert len(result.cognitive.selected_roles) >= 1
    response = result.conversation[-1].content if result.conversation and result.conversation[-1].role == "assistant" else ""
    assert response != "" and "I'm sorry, I am not able to answer your request." not in response
    
    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation, "logs/compare.png")

def test_full_workflow_compare_additional_checks(empty_state):
    state = replace(empty_state)

    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = ["model_0", "model_3"]

    state.cognitive.data = {}
    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/test_1.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    message="Did overturism improve in the scenario-1 compared to base?"
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message

    result_dict = app.invoke(state)
    result = to_state(result_dict)
    assert result.cognitive.next_action == "COMPARE_SCENARIOS"
    assert len(result.cognitive.selected_roles) >= 1
    response = result.conversation[-1].content if result.conversation and result.conversation[-1].role == "assistant" else ""
    assert response != "" and "I'm sorry, I am not able to answer your request." not in response
    correct = False
    check = ["yes", "decreased", "improved"]
    response = result.conversation[-1].content if result.conversation[-1].role == "assistant" else ""
    if any(string in response.lower() for string in check):
        correct = True
    assert correct
    