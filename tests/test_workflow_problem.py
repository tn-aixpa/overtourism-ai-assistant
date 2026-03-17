from app.agent.state import AgentState
from app.config import DRAW_CONVERSATION

message = "I want to create a new problem."

def setup_problem_info(state: AgentState):
    state.cognitive.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem", "required": True},
        "available_subsystems": {"description": "The available subsystems", "required": False},
        "additional_data": {"description": "Additional data", "required": False},
    }
    return state


def test_problem_creation_without_scenarios(agent):
    try:
        agent.state = setup_problem_info(agent.state)

        result = (
            agent.start(message)
                .reply("The problem is that there are not enough parking spaces in Molveno, and the objective is to reduce the number of complaints.")
                .reply("Yes, please.")
                .reply("No")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/problem_creation_no_scenarios.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_problem_creation_without_scenarios.json")

    assert result.state.cognitive.problem_id is not None


def test_problem_creation_with_agentic_scenarios(agent):
    try:
        agent.state = setup_problem_info(agent.state)

        result = (
            agent.start(message)
                .reply("The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues.")
                .reply("Yes, please.")
                .reply("Yes, please suggest 3 scenarios to solve this problem.")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/debug_test_problem_creation_with_agentic_scenarios.png")

        #assert result.state.cognitive.problem_id is not None
        # #assert len(result.state.cognitive.scenarios_to_generate) > 0
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/problem_creation_agentic_scenarios_state.json")


def test_problem_creation_with_user_scenarios(agent):
    try:
        agent.state = setup_problem_info(agent.state)
        agent.state.cognitive.problem_id = "parcheggi_200"
        agent.state.cognitive.scenario_info_to_extract = {
            "title": {"description": "The title of the scenario", "required": True},
            "description": {"description": "Describes the proposal", "required": False},
            "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
            "context_conditions": {"description": "Elements/factors that can impact the solution", "required": False},
            "potential_impact": {"description": "Potential impact of the proposal", "required": False},
            "indexes_to_change": {"description": "Indexes of simulation to change", "required": True},
        }

        with open("tests/data/test_base.json") as f:
            from app.utils.data import parse_data
            import json
            agent.state = parse_data(agent.state, json.load(f), True)

        result = (
            agent.start(message)
                .reply("The problem is that there are not enough parking spaces in Molveno, which leads to people parking off-spot and long queues.")
                .reply("Yes, please.")
                .reply("I want to create a two scenarios: one where I increase parking spaces of 200 units, and the other in which I decrease them of 50.")
                .reply("Yes, proceed.")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/problem_creation_user_scenarios.png")

        #assert result.state.cognitive.problem_id is not None
        # #assert len(result.state.cognitive.scenarios_to_generate) > 0
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_problem_creation_with_user_scenarios.json")