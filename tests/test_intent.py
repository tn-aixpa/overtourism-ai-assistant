import pytest
from dataclasses import replace

from app.agent.nodes.intent import intent_node
from app.agent.nodes.validate_intent import validate_intent_node
from app.agent.state import AgentState


@pytest.mark.parametrize(
    "user_message, active_simulations, expected_intent",
    [
        # --- INTERACT_SIMULATION (single active simulation) ---
        ("Explain the results of simulation simA", ["simA"], "INTERACT_SIMULATION"),
        ("Summarize the results of simulation simA", ["simA"], "INTERACT_SIMULATION"),
        ("Analyze the outcome of simA", ["simA"], "INTERACT_SIMULATION"),
        ("Analyze the outcome of simA", ["simA"], "INTERACT_SIMULATION"),

        # --- COMPARE_SIMULATIONS (multiple active simulations) ---
        ("Compare ther results of the two simulations simA and simB", ["simA", "simB"], "COMPARE_SIMULATIONS"),
        ("Explain the differences between simA and simB", ["simA", "simB"], "COMPARE_SIMULATIONS"),

        # --- RUN_NEW_SIMULATION ---
        ("Run a new simulation with increased parking capacity", [], "RUN_NEW_SIMULATION"),
        ("Start a new simulation with default parameters", ["simA"], "RUN_NEW_SIMULATION"),
        ("Modify simA to use a different parameter", ["simA"], "RUN_NEW_SIMULATION"),

        # --- INVALID (totally unclear) ---
        ("Do the thing for me", [], "INVALID"),
        ("Blah blah blah", [], "INVALID"),

        # --- INVALID (clear but unrelated to simulations) ---
        ("What is the French Revolution?", [], "INVALID"),
        ("Tell me about the weather in Paris", ["simA"], "INVALID"),
    ],
)

def test_intent_classification(empty_state: AgentState, user_message, active_simulations, expected_intent):
    # Copy base state safely
    state = replace(empty_state)

    # Set message
    state.user_message = user_message

    # Set active simulations
    if active_simulations:
        state.sim_ids = active_simulations

    # Run nodes
    state = intent_node(state)
    state = validate_intent_node(state)

    assert state.next_action == expected_intent
