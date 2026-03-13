# tests/test_workflow_scenario.py
import json

from app.agent.state import AgentState
from app.agent.graph import app
from app.utils.data import parse_data
from app.config import DRAW_CONVERSATION
from tests.utils.agent_runner import AgentTestRunner

def setup_scenario_info(state: AgentState):
    state.cognitive.scenario_info_to_extract = {
        "title": {"description": "The title of the scenario", "required": True},
        "description": {"description": "Describes the proposal", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem, links or attachments", "required": False},
        "context_conditions": {"description": "Elements/factors that can impact the proposed solution", "required": False},
        "potential_impact": {"description": "Potential impact of the proposal", "required": False},
        "indexes_to_change": {"description": "Indexes of simulation to change", "required": True}
    }
    return state

def test_scenario_extraction(empty_state):
    # Initialize agent runner
    agent = AgentTestRunner(app, empty_state)

    # Setup problem and scenario extraction info
    agent.state.cognitive.problem_id = "parcheggi_200"
    agent.state = setup_scenario_info(agent.state)

    # Preload base data if needed
    with open("tests/data/test_base.json", "r") as f:
        agent.state = parse_data(agent.state, json.load(f), True)

    # Simulate user message to create two scenarios
    user_message = (
        "I want to create a two scenarios: one where I increase parking spaces of 200 units, "
        "and the other in which I decrease them of 50"
    )

    # Run the multi-turn workflow
    result = (
        agent.start(user_message)
             .reply("Yes, proceed.")  # user confirms scenario
             .run()
    )

    # Optionally draw conversation for debugging
    if DRAW_CONVERSATION:
        from other.drawing_util import draw_conversation
        draw_conversation(result.messages, "logs/scenario_creation.png")

    # Assertions
    assert result.state.cognitive.problem_id == "parcheggi_200"
    #assert len(result.state.cognitive.scenarios_to_generate) > 0