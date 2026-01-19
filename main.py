from app.agent.graph import app

def test():
    state = {
        "user_message": "Please, summarize the simulation results.",
        "sim_ids": ["sim1"],
        "simulation_data": None,
        "simulation_data_loaded_at": None,
        "pending_inputs": {},
        "missing_inputs": [],
        "awaiting_confirmation": False,
        "running_simulation": False,
        "next_action": None,
        "response": "",
    }

    result = app.invoke(state)
    print("\n=== AGENT RESPONSE ===")
    print(result["response"])

def draw():
    print(app.get_graph().draw_mermaid())


draw()