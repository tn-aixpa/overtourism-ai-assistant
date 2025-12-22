from nodes.compare import compare_simulations

def test_compare(empty_state):
    empty_state["sim1"] = "simA"
    empty_state["sim2"] = "simB"
    state = compare_simulations(empty_state)
    assert "Comparing simulations" in state["response"]
