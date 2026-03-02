import pytest
from dataclasses import replace
import json
from app.agent.graph import app
from app.utils.data import parse_data
from app.config import DRAW_CONVERSATION
from app.utils.common import to_state, translate_to_eng
from app.utils.error_codes import ErrorCode, get_error_message

# ---------- TEST: INVALID REQUEST ----------
@pytest.mark.parametrize(
    "message, language",
    [
        ("Tell me about the weather in Paris", "English"),
        ("Come è il meteo a Parigi?", "Italian"),
    ]
)
def test_full_workflow_invalid_localized(empty_state, message, language):
    state = replace(empty_state)
    state.user_lang = language
    state.add_user_message(message, translate_to_eng(message, language))


    result_dict = app.invoke(state)
    result = to_state(result_dict)

    last_message = result.get_last_message()
    response = last_message.content_localized if last_message and last_message.role == "assistant" else ""
    assert response == get_error_message(ErrorCode.INVALID_REQUEST, language)

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation.messages, f"logs/invalid_{language}.png")


# ---------- TEST: INTERACT ----------
@pytest.mark.parametrize(
    "message, language",
    [
        ("What is the most critical constraint and what does this imply?", "English"),
        ("Qual è il vincolo più critico e cosa implica?", "Italian")
    ]
)
def test_full_workflow_interact_localized(empty_state, message, language):
    state = replace(empty_state)
    state.user_lang = language
    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = ["model_0"]

    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.add_user_message(message, translate_to_eng(message, language))

    result_dict = app.invoke(state)
    result = to_state(result_dict)

    assert result.cognitive.next_action == "INTERACT_SCENARIO"
    assert len(result.cognitive.selected_roles) >= 1

    last_message = result.get_last_message()
    response = last_message.content_en if last_message and last_message.role == "assistant" else ""
    assert response != "" and "not able to handle this request" not in response and "parking" in response.lower()

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation.messages, f"logs/interact_{language}.png")


# ---------- TEST: COMPARE ----------
@pytest.mark.parametrize(
    "message, language",
    [
        ("What changed between the two scenarios and what was the impact of the change?", "English"),
        ("Cosa è cambiato tra i due scenari e quale è stato l'impatto del cambiamento?", "Italian")
    ]
)
def test_full_workflow_compare_localized(empty_state, message, language):
    state = replace(empty_state)
    state.user_lang = language
    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = ["model_0", "model_3"]
    state.cognitive.data = {}

    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/test_1.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.add_user_message(message, translate_to_eng(message, language))

    result_dict = app.invoke(state)
    result = to_state(result_dict)

    assert result.cognitive.next_action == "COMPARE_SCENARIOS"
    assert len(result.cognitive.selected_roles) >= 1

    last_message = result.get_last_message()
    response = last_message.content_en if last_message and last_message.role == "assistant" else ""
    assert response != "" and "I'm sorry, I am not able to answer your request." not in response

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation.messages, f"logs/compare_{language}.png")


# ---------- TEST: COMPARE ADDITIONAL CHECKS ----------
@pytest.mark.parametrize(
    "message, check_words, language",
    [
        ("Did overturism improve in the scenario-1 compared to base?", ["yes", "decreased", "improved"], "English"),
        ("Il sovraffollamento turistico è migliorato nello scenario-1 rispetto al base?", ["sì", "diminuì", "migliorato"], "Italian")
    ]
)
def test_full_workflow_compare_additional_checks_localized(empty_state, message, check_words, language):
    state = replace(empty_state)
    state.user_lang = language
    state.cognitive.problem_id = "parcheggi_200"
    state.cognitive.scenario_ids = ["model_0", "model_3"]
    state.cognitive.data = {}

    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/test_1.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))

    state.add_user_message(message, message)

    result_dict = app.invoke(state)
    result = to_state(result_dict)

    assert result.cognitive.next_action == "COMPARE_SCENARIOS"
    assert len(result.cognitive.selected_roles) >= 1

    last_message = result.get_last_message()
    response = last_message.content_localized if last_message and last_message.role == "assistant" else ""

    correct = any(word in response.lower() for word in check_words)
    assert response != "" and correct

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation.messages, f"logs/compare_additional_{language}.png")