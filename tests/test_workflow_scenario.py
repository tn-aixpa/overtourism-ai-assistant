from app.config import DRAW_CONVERSATION

def test_scenario_extraction(agent):
    try:
        result = (
            agent.start("Please, activate proposal_1")
                .reply("I want to create a new scenario with the following:\n- Title: Parking facility\n- Description: create a new parking facility that will increase parking availability and reduce traffic in the city center\n- Index change: `available_parking_spaces` range [350-850]")
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
