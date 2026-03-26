from app.agent.state import AgentState
from app.config import DRAW_CONVERSATION

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

def test_scenario_extraction(agent):
    try:
        # Setup problem and scenario extraction info
        agent.state = setup_scenario_info(agent.state)


        result = (
            agent.start("Please, activate parcheggi_200")
                .reply("I want to create two new scenarios: one where I increase available parking spaces of 200 units and the other in which I decrease them of 50")
                .reply("Yes, please.")
                .run()
        )

        # Optionally draw conversation for debugging
        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/scenario_creation.png")

        # Assertions
        #WARNING: this test might require revision when impementing scenario running
        runned_scenarios = len([trace for trace in result.state.cognitive.trace.steps if trace.node == "run_scenario_node"])
        assert runned_scenarios == 2
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/scenario_debug.json")
