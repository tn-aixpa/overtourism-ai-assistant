import pytest
from dataclasses import replace

from nodes.intent import intent_node
from nodes.validate_intent import validate_intent_node
from state import AgentState


@pytest.mark.parametrize(
    "user_message, active_simulations, expected_intent",
    [
        # --- INTERACT_SIMULATION ---
        ("Explain the results of simulation simA", ["simA"], "INTERACT_SIMULATION")

    ],
)
def test_intent_classification(empty_state: AgentState, user_message, active_simulations, expected_intent):
    # Copy base state safely
    state = replace(empty_state)

    # Set message
    state.user_message = user_message

    # Set active simulations
    if active_simulations:
        state.sim1_id = active_simulations[0]
        if len(active_simulations) > 1:
            state.sim2_id = active_simulations[1]

    # Run nodes
    state = intent_node(state)
    state = validate_intent_node(state)

    assert state.next_action == expected_intent
