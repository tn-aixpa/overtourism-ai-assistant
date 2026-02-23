from dataclasses import replace
from datetime import datetime
import json

from app.agent.graph import app
from app.agent.state import ConversationMessage
from app.utils.data import parse_data
from app.utils.common import to_state
from app.config import DRAW_CONVERSATION

message="I want to create a new problem."

def test_problem_creation_without_scenarios(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_PROBLEM_INPUT":
            return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
        if payload["type"] == "WAIT_CONFIRMATION_PROBLEM":
            return "Yes, please."
        if payload["type"] == "WAIT_SCENARIO_PREFERENCE":
            return "No, I don't want to create scenarios."
        return None

    # Replace interrupt with fake version
    monkeypatch.setattr(
        "app.agent.graphs.utils.interrupt",
        fake_interrupt
    )

    state = replace(empty_state)
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message

    state.cognitive.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
        "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
    }

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        result_dict = app.invoke(state)
        result = to_state(result_dict)
        draw_conversation(result.conversation, "logs/problem_creation_no_scenarios.png")
    else:
        events = []
        with open("logs/test_problem_workflow.log", "w") as f:
            for event in app.stream(state):
                f.write(f"Event: {event}\n")
                events.append(event)
    

def test_problem_creation_with_agentic_scenarios(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_PROBLEM_INPUT":
            return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
        if payload["type"] == "WAIT_CONFIRMATION_PROBLEM":
            return "Yes, please."
        if payload["type"] == "WAIT_SCENARIO_PREFERENCE":
            return "Yes, please suggest 3 scenarios to solve this problem."
        return None

    # Replace interrupt with fake version
    monkeypatch.setattr(
        "app.agent.graphs.utils.interrupt",
        fake_interrupt
    )

    state = replace(empty_state)
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message

    state.cognitive.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
        "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
    }

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        result_dict = app.invoke(state)
        result = to_state(result_dict)
        draw_conversation(result.conversation, "logs/problem_creation_agentic_scenarios.png")
    else:
        events = []
        with open("logs/test_problem_workflow.log", "a+") as f:
            for event in app.stream(state):
                f.write(f"Event: {event}\n")
                events.append(event)

def test_problem_creation_with_user_scenarios(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_PROBLEM_INPUT":
            return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
        if payload["type"] == "WAIT_CONFIRMATION_PROBLEM":
            return "Yes, please."
        if payload["type"] == "WAIT_SCENARIO_PREFERENCE":
            return "I want to create a two scenarios: one where I increase parking spaces of 200 units, and the other in which I decrease them of 50."
        if payload["type"] == "WAIT_CONFIRMATION_SCENARIO":
            return "Yes, proceed."
        return None

    # Replace interrupt with fake version
    monkeypatch.setattr(
        "app.agent.graphs.utils.interrupt",
        fake_interrupt
    )

    state = replace(empty_state)
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message

    state.cognitive.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
        "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
    }

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

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        result_dict = app.invoke(state)
        result = to_state(result_dict)
        draw_conversation(result.conversation, "logs/problem_creation_user_scenarios.png")
    else:
        events = []
        with open("logs/test_problem_workflow.log", "a+") as f:
            for event in app.stream(state):
                f.write(f"Event: {event}\n")
                events.append(event)
