from nodes.interact import interact_simulation

def test_interact(empty_state):
    empty_state.sim1_id = "sim123"
    empty_state.user_message = "Explain the results"
    state = interact_simulation(empty_state)
    assert "simulation" in state.response
