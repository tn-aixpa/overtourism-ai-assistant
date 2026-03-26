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

    # assert result.state.cognitive.problem_id is not None


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

        # assert result.state.cognitive.problem_id is not None
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/problem_creation_agentic_scenarios_state.json")

