# from app.agent.nodes.run_scenario import extract_inputs, ask_missing, confirm, run_scenario

# def test_extract_inputs(empty_state):
#     empty_state.user_message = "Run with model X and duration 100"
#     state = extract_inputs(empty_state)
#     assert "model" in state.pending_inputs

# def test_ask_missing(empty_state):
#     empty_state.missing_inputs = ["model", "duration"]
#     state = ask_missing(empty_state)
#     assert "Missing inputs" in state.response

# def test_confirm(empty_state):
#     empty_state.pending_inputs = {"model": "X", "duration": 100}
#     state = confirm(empty_state)
#     assert "Scenario summary" in state.response

# def test_run_scenario(empty_state):
#     empty_state.pending_inputs = {"model": "X", "duration": 100, "parameters": {}}
#     state = run_scenario(empty_state)
#     assert state.running_scenario is False
