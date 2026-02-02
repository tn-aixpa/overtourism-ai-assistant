from app.agent.graph import app

def test():
    state = {
        "user_message": "Please, summarize the scenario results.",
        "scenario_ids": ["sim1"],
        "data": None,
        "data_loaded_at": None,
        "next_action": None,
        "response": "",
    }

    result = app.invoke(state)
    print("\n=== AGENT RESPONSE ===")
    print(result["response"])

def draw():
    print(app.get_graph().draw_mermaid())


draw()
# use https://mermaid.live/ to visualize the output