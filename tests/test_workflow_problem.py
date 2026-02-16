import pytest
from dataclasses import replace

from app.agent.graph import app
from app.agent.state import AgentState
from tests.conftest import empty_state

DRAW_CONVERSATION = True

# def test_problem_creation_without_scenarios(empty_state, monkeypatch):

#     # Fake human response
#     def fake_interrupt(payload):
#         if payload["type"] == "WAIT_PROBLEM_INPUT":
#             return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
#         if payload["type"] == "WAIT_PROBLEM_CONFIRMATION":
#             return "Yes, please."
#         if payload["type"] == "WAIT_SCENARIO_PREFERENCE":
#             return "No, I don't want to create scenarios."
#         return None

#     # Replace interrupt with fake version
#     monkeypatch.setattr(
#         "app.agent.graphs.utils.interrupt",
#         fake_interrupt
#     )

#     state = replace(empty_state)
#     state.messages = [
#         {
#             "role": "user",
#             "content": "I want to create a new problem.",
#         }
#     ]

#     state.problem_info_to_extract = {
#         "problem_title": {"description": "The title of the problem", "required": True},
#         "objectives": {"description": "The objectives of the problem", "required": True},
#         "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
#         "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
#         "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
#     }

#     if DRAW_CONVERSATION:
#         from other.drawing_util import draw_conversation
#         state=app.invoke(state)
#         draw_conversation(state["messages"], "logs/problem_creation_no_scenarios.png")
#     else:
#         events = []
#         with open("logs/test_problem_workflow.log", "w") as f:
#             for event in app.stream(state):
#                 f.write(f"Event: {event}\n")
#                 events.append(event)
    

def test_problem_creation_without_scenarios(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_PROBLEM_INPUT":
            return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
        if payload["type"] == "WAIT_PROBLEM_CONFIRMATION":
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
    state.messages = [
        {
            "role": "user",
            "content": "I want to create a new problem.",
        }
    ]

    state.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
        "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
    }

    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        state=app.invoke(state)
        draw_conversation(state["messages"], "logs/problem_creation_agentic_scenarios.png")
    else:
        events = []
        with open("logs/test_problem_workflow.log", "a+") as f:
            for event in app.stream(state):
                f.write(f"Event: {event}\n")
                events.append(event)
