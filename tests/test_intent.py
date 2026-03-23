import pytest
from dataclasses import replace

from app.agent.nodes.intent import intent_node, validate_intent_node
from app.agent.state import AgentState

@pytest.mark.parametrize(
    "message, active_scenarios, problem_id,expected_intent, should_raise",
    [
        # --- LIST_AVAILABLE (single active scenario) ---
        ("What problems have been indentified?", [], "", "LIST_AVAILABLE", False),
        ("Can you list which proposals have been made to solve this problem?", [], "", "LIST_AVAILABLE", False),
        ("What scenarios have been identfied?", [], "", "LIST_AVAILABLE", False),
        ("Can you please list what problems, proposals and scenarios are there?", [], "", "LIST_AVAILABLE", False),

        # --- INTERACT_SCENARIO (single active scenario) ---
        ("Explain the results of scenario simA", ["simA"], "P1", "INTERACT_SCENARIO", False),
        ("Summarize the results of scenario simA", ["simA"], "P1", "INTERACT_SCENARIO", False),
        ("Analyze the outcome of simA", ["simA"], "P1", "INTERACT_SCENARIO", False),
        ("Analyze the outcome of simA", ["simA"], "P1", "INTERACT_SCENARIO", False),

        # --- COMPARE_SCENARIOS (multiple active scenarios) ---
        ("Compare ther results of the two scenarios simA and simB", ["simA", "simB"], "P1", "COMPARE_SCENARIOS", False),
        ("Explain the differences between simA and simB", ["simA", "simB"], "P1", "COMPARE_SCENARIOS", False),

        # --- CREATE NEW PROBLEM ---
        ("Create a new problem related to Molveno overtourism and in particular focus on beach usage", [], "", "CREATE_NEW_PROBLEM", False),
        ("I want to define a new problem related to traffic congestion", [], "", "CREATE_NEW_PROBLEM", False),
        ("There is a new issue regarding parking usage that needs to be addressed", [], "", "CREATE_NEW_PROBLEM", False),
        ("In Molveno there is a problem related to the fact that there are not enough parking spaces which leads to people parking off-spot and long queues. The administration would like to have 3 different strategies to tackle this problem.", [], "", "CREATE_NEW_PROBLEM", False),

        # --- CREATE_NEW_SCENARIO ---
        ("Run a new scenario with increased parking capacity", [], "P1", "CREATE_NEW_SCENARIO", False),
        ("Modify simA to use a different parameter", ["simA"], "P1", "CREATE_NEW_SCENARIO", False),

        # --- INVALID (totally unclear) ---
        ("Do the thing for me", [], "", "INVALID", True),
        ("Blah blah blah", [], "", "INVALID", True),

        # --- INVALID (clear but unrelated to scenarios) ---
        ("What is the French Revolution?", [], "", "INVALID", True),
        ("Tell me about the weather in Paris", ["simA"], "", "INVALID", True),
    ],
)

def test_intent_classification(empty_state: AgentState, message, active_scenarios, problem_id, expected_intent, should_raise):
    # Copy base state safely
    state = replace(empty_state)

    # Set variables
    state.add_user_message(message, message)
    state.cognitive.problem_id = problem_id    

    # Set active scenarios
    if active_scenarios:
        state.cognitive.scenario_ids = active_scenarios

    # Run nodes
    state = intent_node(state)
    if should_raise:
        with pytest.raises(Exception):
            validate_intent_node(state)
    else:
        state = validate_intent_node(state)
        assert state.cognitive.next_action == expected_intent
