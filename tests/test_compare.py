from nodes.compare import compare_simulations

def test_compare(empty_state):
    empty_state.sim1_id = "simA"
    empty_state.sim2_id = "simB"
    state = compare_simulations(empty_state)
    assert "Comparing simulations" in state.response
