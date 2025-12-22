from graph import app

state = {
    "user_message": "Run a simulation with model and duration and parameters",
    "simulation_id": None,
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
