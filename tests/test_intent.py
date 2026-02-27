import pytest
from datetime import datetime
from dataclasses import replace

from app.agent.nodes.intent import intent_node, validate_intent_node
from app.agent.state import AgentState, ConversationMessage

@pytest.mark.parametrize(
    "message, active_scenarios, problem_id,expected_intent, should_raise",
    [
        # --- INTERACT_SCENARIO (single active scenario) ---
        ("Explain the results of scenario simA", ["simA"], "P1", "INTERACT_SCENARIO", False),
        ("Summarize the results of scenario simA", ["simA"], "P1", "INTERACT_SCENARIO", False),
        ("Analyze the outcome of simA", ["simA"], "P1", "INTERACT_SCENARIO", False),
        ("Analyze the outcome of simA", ["simA"], "P1", "INTERACT_SCENARIO", False),

        # --- COMPARE_SCENARIOS (multiple active scenarios) ---
        ("Compare ther results of the two scenarios simA and simB", ["simA", "simB"], "P1", "COMPARE_SCENARIOS", False),
        ("Explain the differences between simA and simB", ["simA", "simB"], "P1", "COMPARE_SCENARIOS", False),

        # --- CREATE NEW PROBLEM ---
        ("Create a new problem related to Molveno overtourism and in particular focus on beach usage", [], "", "CREATE_PROBLEM", False),
        ("I want to define a new problem related to traffic congestion", [], "", "CREATE_PROBLEM", False),
        ("There is a new issue regarding parking usage that needs to be addressed", [], "", "CREATE_PROBLEM", False),
        ("In Molveno there is a problem related to the fact that there are not enough parking spaces which leads to people parking off-spot and long queues. The administration would like to have 3 different strategies to tackle this problem.", [], "", "CREATE_PROBLEM", False),


        # --- RUN_NEW_SCENARIO ---
        ("Run a new scenario with increased parking capacity", [], "P1", "RUN_NEW_SCENARIO", False),
        ("Start a new scenario with default parameters", ["simA"], "P1", "RUN_NEW_SCENARIO", False),
        ("Modify simA to use a different parameter", ["simA"], "P1", "RUN_NEW_SCENARIO", False),

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
    state.conversation.append(
        ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.now()
    ))
    state.last_user_en = message
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
