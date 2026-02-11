import pytest
from dataclasses import replace

from app.agent.graph import app
from app.agent.state import AgentState
from tests.conftest import empty_state

# def test_problem_creation_without_scenarios(empty_state, monkeypatch):

#     # Fake human response
#     def fake_interrupt(payload):
#         if payload["type"] == "WAIT_PROBLEM_INPUT":
#             return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
#         if payload["type"] == "WAIT_PROBLEM_CONFIRMATION":
#             return "Yes, proceed."
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
#             "content": (
#                 "I want to create a new problem.",
#             )
#         }
#     ]

#     state.problem_info_to_extract = {
#         "problem_title": {"description": "The title of the problem", "required": True},
#         "objectives": {"description": "The objectives of the problem", "required": True},
#         "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
#         "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
#         "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
#     }

#     events = []

#     with open("logs/test_problem_workflow.log", "w") as f:
#         for event in app.stream(state):
#             f.write(f"Event: {event}\n")
#             events.append(event)

def test_problem_creation_without_scenarios(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_PROBLEM_CONFIRMATION":
            return "Yes, proceed."
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
            "content": (
                "In Molveno there is a problem related to the fact that there are not enough parking spaces",
                 "which leads to people parking off-spot and long queues.",
            )
        }
    ]

    state.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": False},
        "problem_description": {"description": "A detailed description of the problem", "required": True},
        "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
    }

    events = []

    with open("logs/test_problem_workflow.log", "w") as f:
        for event in app.stream(state):
            f.write(f"Event: {event}\n")
            events.append(event)


#state.user_message = "In Molveno there is a problem related to the fact that there are not enough parking spaces which leads to people parking off-spot and long queues. The administration would like to have 3 different strategies to tackle this problem.