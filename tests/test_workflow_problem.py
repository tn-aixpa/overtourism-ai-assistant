from app.agent.state import AgentState
from app.config import DRAW_CONVERSATION

message = "I want to create a new problem."


def test_problem_creation(agent):
    try:
        result = (
            agent.start(message)
                .reply("These are the required informations:\n- Title: overtoruism in Molveno\n- Objectives: reduce traffic and congestion\n- Problem description: too many access with cars are registered in the city center")
                .reply("Yes, please.")
                .run()
        )

        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/problem_creation.png")
    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/debug_test_problem_creation.json")
