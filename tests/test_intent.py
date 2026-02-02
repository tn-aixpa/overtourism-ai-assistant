import pytest
from dataclasses import replace

from app.agent.nodes.intent import intent_node
from app.agent.nodes.validate_intent import validate_intent_node
from app.agent.state import AgentState


@pytest.mark.parametrize(
    "user_message, active_scenarios, expected_intent",
    [
        # --- INTERACT_SCENARIO (single active scenario) ---
        ("Explain the results of scenario simA", ["simA"], "INTERACT_SCENARIO"),
        ("Summarize the results of scenario simA", ["simA"], "INTERACT_SCENARIO"),
        ("Analyze the outcome of simA", ["simA"], "INTERACT_SCENARIO"),
        ("Analyze the outcome of simA", ["simA"], "INTERACT_SCENARIO"),

        # --- COMPARE_SCENARIOS (multiple active scenarios) ---
        ("Compare ther results of the two scenarios simA and simB", ["simA", "simB"], "COMPARE_SCENARIOS"),
        ("Explain the differences between simA and simB", ["simA", "simB"], "COMPARE_SCENARIOS"),

        # --- RUN_NEW_SCENARIO ---
        ("Run a new scenario with increased parking capacity", [], "RUN_NEW_SCENARIO"),
        ("Start a new scenario with default parameters", ["simA"], "RUN_NEW_SCENARIO"),
        ("Modify simA to use a different parameter", ["simA"], "RUN_NEW_SCENARIO"),

        # --- INVALID (totally unclear) ---
        ("Do the thing for me", [], "INVALID"),
        ("Blah blah blah", [], "INVALID"),

        # --- INVALID (clear but unrelated to scenarios) ---
        ("What is the French Revolution?", [], "INVALID"),
        ("Tell me about the weather in Paris", ["simA"], "INVALID"),
    ],
)

def test_intent_classification(empty_state: AgentState, user_message, active_scenarios, expected_intent):
    # Copy base state safely
    state = replace(empty_state)

    # Set message
    state.user_message = user_message

    # Set active scenarios
    if active_scenarios:
        state.scenario_ids = active_scenarios

    # Run nodes
    state = intent_node(state)
    state = validate_intent_node(state)

    assert state.next_action == expected_intent
