from dataclasses import replace
from datetime import datetime
import json

from app.agent.graph import app
from app.utils.data import parse_data
from app.agent.state import ConversationMessage
from app.utils.common import to_state
from app.config import DRAW_CONVERSATION

def test_scenario_extraction(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_CONFIRMATION_SCENARIO":
            return "Yes, proceed."
        return None

    # Replace interrupt with fake version
    monkeypatch.setattr(
        "app.agent.graphs.utils.interrupt",
        fake_interrupt
    )

    # Definitions
    state = replace(empty_state)
    
    state.cognitive.problem_id = "parcheggi_200"

    state.cognitive.scenario_info_to_extract = {
        "title": {"description": "The title of the scenario", "required": True},
        "description": {"description": "Describes the proposal", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem, links or attachments", "required": False},
        "context_conditions": {"description": "Elements/factors that can impact the proposed solution", "required": False},
        "potential_impact": {"description": "Potential impact of the proposal", "required": False},
        "indexes_to_change": {"description": "Indexes of simulation to change", "required": True}
    }


    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()), True)

    message="I want to create a two scenarios: one where I increase parking spaces of 200 units, and the other in which I decrease them of 50 "
    state.add_user_message(message, message)

    events = []

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        result_dict = app.invoke(state)
        result = to_state(result_dict)
        draw_conversation(result.conversation.messages, "logs/scenario_creation.png")
    else:
        events = []
        with open("logs/test_scenario_workflow.log", "a+") as f:
            for event in app.stream(state):
                f.write(f"Event: {event}\n")
                events.append(event)