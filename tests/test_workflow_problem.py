from app.agent.state import AgentState
from app.config import DRAW_CONVERSATION

message = "I want to create a new problem."


def test_problem_creation(agent):
    try:
        result = (
            agent.start(message)
                .reply("The problem is that there are not enough parking spaces in Molveno, and the objective is to reduce the number of complaints.")
                .reply("Yes, please.")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/problem_creation.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_problem_creation.json")
