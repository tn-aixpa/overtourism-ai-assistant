from app.config import DRAW_CONVERSATION

def test_scenario_extraction(agent):
    try:
        result = (
            agent.start("Please, activate parcheggi_200")
                .reply("I want to create two new scenarios: one where I increase available parking spaces of 200 units and the other in which I decrease them of 50")
                .reply("No, cancel")
                .run()
        )

        # Optionally draw conversation for debugging
        if DRAW_CONVERSATION:
            from other.drawing_util import draw_conversation
            draw_conversation(result.messages, "logs/scenario_creation.png")

    finally:
        agent.state.save()
        agent.state.dump_to_file("logs/scenario_debug.json")
