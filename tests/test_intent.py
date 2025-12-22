from nodes.intent import intent_node

def test_intent_classification(empty_state):
    empty_state["user_message"] = "Compare two simulations simA and simB"
    state = intent_node(empty_state)
    assert state["next_action"] in [
        "INTERACT_SIMULATION",
        "COMPARE_SIMULATIONS",
        "RUN_NEW_SIMULATION",
        "ASK_CLARIFICATION",
    ]
