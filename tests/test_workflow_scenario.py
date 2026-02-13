import pytest
from dataclasses import replace
from datetime import datetime
import json

from app.agent.graph import app
from app.utils.data import parse_data
from app.agent.state import AgentState
from tests.conftest import empty_state

def test_scenario_extraction(empty_state, monkeypatch):

    # Fake human response
    def fake_interrupt(payload):
        if payload["type"] == "WAIT_SCENARIO_INPUT":
            return "The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues."
        if payload["type"] == "WAIT_SCENARIO_CONFIRMATION":
            return "Yes, proceed."
        return None

    # Replace interrupt with fake version
    monkeypatch.setattr(
        "app.agent.graphs.utils.interrupt",
        fake_interrupt
    )

    # Definitions
    state = replace(empty_state)
    
    state.problem_id = "parcheggi_200"
    state.data_loaded_at = datetime.now()

    state.scenario_info_to_extract = {
        "title": {"description": "The title of the scenario", "required": True},
        "description": {"description": "Describes the proposal", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem, links or attachments", "required": False},
        "context_conditions": {"description": "Elements/factors that can impact the proposed solution", "required": False},
        "potential_impact": {"description": "Potential impact of the proposal", "required": False},
        "indexes_to_change": {"description": "Indexes of simulation to change", "required": True}
    }


    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()), True)


    #"I want to create a new scenario where I increase parking spaces of 200 units",
    state.messages = [
        {
            "role": "user",
            "content": (
                "I want to create a two scenarios: one where I increase parking spaces of 200 units, and the other in which I decrease them of 50 ",
            )
        }
    ]

    events = []

    with open("logs/test_problem_workflow.log", "w") as f:
        for event in app.stream(state):
            f.write(f"Event: {event}\n")
            events.append(event)

