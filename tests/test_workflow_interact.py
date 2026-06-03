import pytest
from dataclasses import replace

from app.agent.graph import app
from app.config import DRAW_CONVERSATION
from app.utils.common import to_state

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
    state.add_user_message(message)


    result_dict = app.invoke(state)
    result = to_state(result_dict)

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.conversation.messages, f"logs/invalid_{language}.png")


# ---------- TEST: INTERACT ----------

def test_full_workflow_interact(agent):
    try:
        agent.session_id = "fakdfkl"
        result = (
            agent.start("What are the available scenarios?")
                .reply("Plase, activate scenario scenario_base")
                .reply("What is the most critical constraint?")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/interact_english.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_full_workflow_interact.json")

    last_message = result.state.get_last_message()
    response = last_message.content if last_message and last_message.role == "assistant" else ""

    assert result.state.cognitive.next_action == "INTERACT_CONTEXT"

def test_full_workflow_interact_italian(agent):
    try:
        agent.state.user_lang = "Italian"
        result = (
            agent.start("Quali sono gli scenari disponibili?")
                .reply("Per favore, attiva lo scenario scenario_base")
                .reply("Quale è l'indice con maggior criticità?")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/interact_italian.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_full_workflow_interact_it.json")

    assert result.state.cognitive.next_action == "INTERACT_CONTEXT"

# ---------- TEST: COMPARE ----------
def test_full_workflow_compare(agent):
    try:
        agent.session_id = "fakdfkl"
        result = (
            agent.start("What are the available scenarios?")
                .reply("Plase, activate scenario_base and scenario_allargamento_parcheggi_300")
                .reply("What is the difference between the two?")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/compare_english.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_full_workflow_compare.json")

    assert result.state.cognitive.next_action == "INTERACT_CONTEXT"

def test_full_workflow_interact_italian(agent):
    try:
        agent.state.user_lang = "Italian"
        result = (
            agent.start("Quali sono gli scenari disponibili?")
                .reply("Per favore, attiva gli scenari scenario_base e scenario_allargamento_parcheggi_300")
                .reply("Quali sono le principali differenze fra le due?")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/compare_italian.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_full_workflow_compare_it.json")

    last_message = result.state.get_last_message()
    response = last_message.content if last_message and last_message.role == "assistant" else ""

    assert result.state.cognitive.next_action == "INTERACT_CONTEXT"
    assert response != "" and "not able to handle this request" not in response