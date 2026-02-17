from dataclasses import replace
from datetime import datetime
import json

from app.agent.graph import app
from app.agent.state import AgentState
from app.utils.data import parse_data
from app.config import DRAW_CONVERSATION

# def test_full_workflow_invalid(empty_state):
#     state = replace(empty_state)
#     state.messages = [{"role": "user", "content": "Tell me about the weather in Paris"}]

#     result = app.invoke(state)
#     response = result["messages"][-1]["content"] if result["messages"] and result["messages"][-1]["role"] == "assistant" else ""
#     assert response == "I'm not able to handle this request with the current system capabilities."

#     if DRAW_CONVERSATION:
#         from other.drawing_util import draw_conversation
#         draw_conversation(result["messages"], "logs/invalid.png")

# def test_full_workflow_interact(empty_state):

#     state = replace(empty_state)
    
#     state.problem_id = "parcheggi_200"
#     state.scenario_ids = ["model_0"]
#     state.data_loaded_at = datetime.now()

#     with open(f"tests/data/test_base.json", "r") as f:
#         state = parse_data(state, json.loads(f.read()))

#     state.messages.append({"role": "user", "content": "What is the most critical constraint and what does this imply?"})

#     result = app.invoke(state)

#     assert result["next_action"] == "INTERACT_SCENARIO"
#     assert len(result["selected_roles"]) >= 1
#     response = result["messages"][-1]["content"] if result["messages"] and result["messages"][-1]["role"] == "assistant" else ""
#     assert response != "" and "not able to handle this request" not in response and "parking" in response

#     if DRAW_CONVERSATION:
#         from other.drawing_util import draw_conversation
#         draw_conversation(result["messages"], "logs/interact.png")
    
    
def test_full_workflow_compare(empty_state):
    state = replace(empty_state)

    state.problem_id = "parcheggi_200"
    state.scenario_ids = ["model_0", "model_3"]
    state.data_loaded_at = datetime.now()

    state.data = {}
    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/test_1.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.messages.append({"role": "user", "content": "Please, what changed between the two scenarios and what was the impact of the change."})

    result = app.invoke(state)
    assert result["next_action"] == "COMPARE_SCENARIOS"
    assert len(result["selected_roles"]) >= 1
    response = result["messages"][-1]["content"] if result["messages"] and result["messages"][-1]["role"] == "assistant" else ""
    assert response != "" and "not able to handle this request" not in response

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result["messages"], "logs/compare.png")
