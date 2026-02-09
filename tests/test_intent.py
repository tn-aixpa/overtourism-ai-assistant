import pytest
from dataclasses import replace

from app.agent.nodes.intent import intent_node, validate_intent_node
from app.agent.state import AgentState

# TODO add tests for CREATE_PROBLEM

@pytest.mark.parametrize(
    "user_message, active_scenarios, problem_id,expected_intent",
    [
        # --- INTERACT_SCENARIO (single active scenario) ---
        ("Explain the results of scenario simA", ["simA"], "P1", "INTERACT_SCENARIO"),
        ("Summarize the results of scenario simA", ["simA"], "P1", "INTERACT_SCENARIO"),
        ("Analyze the outcome of simA", ["simA"], "P1", "INTERACT_SCENARIO"),
        ("Analyze the outcome of simA", ["simA"], "P1", "INTERACT_SCENARIO"),

        # --- COMPARE_SCENARIOS (multiple active scenarios) ---
        ("Compare ther results of the two scenarios simA and simB", ["simA", "simB"], "P1", "COMPARE_SCENARIOS"),
        ("Explain the differences between simA and simB", ["simA", "simB"], "P1", "COMPARE_SCENARIOS"),

        # --- CREATE NEW PROBLEM ---
        ("Create a new problem related to Molveno overtourism and in particular focus on beach usage", [], "", "CREATE_PROBLEM"),
        ("I want to define a new problem related to traffic congestion", [], "", "CREATE_PROBLEM"),
        ("There is a new issue regarding parking usage that needs to be addressed", [], "", "CREATE_PROBLEM"),
        ("In Molveno there is a problem related to the fact that there are not enough parking spaces which leads to people parking off-spot and long queues. The administration would like to have 3 different strategies to tackle this problem.", [], "", "CREATE_PROBLEM"),


        # --- RUN_NEW_SCENARIO ---
        ("Run a new scenario with increased parking capacity", [], "P1", "RUN_NEW_SCENARIO"),
        ("Start a new scenario with default parameters", ["simA"], "P1", "RUN_NEW_SCENARIO"),
        ("Modify simA to use a different parameter", ["simA"], "P1", "RUN_NEW_SCENARIO"),

        # --- INVALID (totally unclear) ---
        ("Do the thing for me", [], "", "INVALID"),
        ("Blah blah blah", [], "", "INVALID"),

        # --- INVALID (clear but unrelated to scenarios) ---
        ("What is the French Revolution?", [], "", "INVALID"),
        ("Tell me about the weather in Paris", ["simA"], "", "INVALID"),
    ],
)

def test_intent_classification(empty_state: AgentState, user_message, active_scenarios, problem_id, expected_intent):
    # Copy base state safely
    state = replace(empty_state)

    # Set variables
    state.user_message = user_message
    state.problem_id = problem_id    

    # Set active scenarios
    if active_scenarios:
        state.scenario_ids = active_scenarios

    # Run nodes
    state = intent_node(state)
    state = validate_intent_node(state)

    assert state.next_action == expected_intent
