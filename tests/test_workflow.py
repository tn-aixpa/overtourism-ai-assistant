from app.agent.graph import app

def test_full_workflow():
    state = {
        "user_message": "Run a simulation with model X and duration 100",
        "sim1_id": None,
        "sim2_id": None,
        "pending_inputs": {},
        "missing_inputs": [],
        "awaiting_confirmation": False,
        "running_simulation": False,
        "next_action": None,
        "response": "",
    }
    result = app.invoke(state)
    assert result["response"] is not None
