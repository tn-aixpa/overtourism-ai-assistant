from nodes.run_simulation import extract_inputs, ask_missing, confirm, run_simulation

def test_extract_inputs(empty_state):
    empty_state["user_message"] = "Run with model X and duration 100"
    state = extract_inputs(empty_state)
    assert "model" in state["pending_inputs"]

def test_ask_missing(empty_state):
    empty_state["missing_inputs"] = ["model", "duration"]
    state = ask_missing(empty_state)
    assert "Missing inputs" in state["response"]

def test_confirm(empty_state):
    empty_state["pending_inputs"] = {"model": "X", "duration": 100}
    state = confirm(empty_state)
    assert "Simulation summary" in state["response"]

def test_run_simulation(empty_state):
    empty_state["pending_inputs"] = {"model": "X", "duration": 100, "parameters": {}}
    state = run_simulation(empty_state)
    assert state["simulation_id"] is not None
    assert state["running_simulation"] is False
