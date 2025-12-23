from graph import app

state = {
    "user_message": "Run a simulation with model and duration and parameters",
    "simulation_id": None,
    "simulation_data": None,
    "simulation_data_loaded_at": None,
    "interact_blocked_until": None,
    "sim1": None,
    "sim2": None,
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
