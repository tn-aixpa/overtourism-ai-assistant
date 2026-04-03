import pytest
from dataclasses import replace

from app.agent.nodes.intent import intent_node
from app.agent.state import AgentState

@pytest.mark.parametrize(
    "message, expected_intent, should_raise",
    [
        # --- LIST_AVAILABLE (single active scenario) ---
        ("What problems have been indentified?", "LIST_AVAILABLE", False),
        ("Can you list which proposals have been made to solve this problem?", "LIST_AVAILABLE", False),
        ("What scenarios have been identfied?", "LIST_AVAILABLE", False),
        ("Can you please list what problems, proposals and scenarios are there?", "LIST_AVAILABLE", False),

        # --- INTERACT_CONTEXT ---
        ("Explain the results of scenario simA", "INTERACT_CONTEXT", False),
        ("Analyze the outcome of simA", "INTERACT_CONTEXT", False),
        ("Compare ther results of the two scenarios simA and simB", "INTERACT_CONTEXT", False),
        ("Explain the differences between the scenarios", "INTERACT_CONTEXT", False),

        # --- CREATE NEW PROBLEM ---
        ("In Molveno there is a problem related to the fact that there are not enough parking spaces which leads to people parking off-spot and long queues. The administration would like to have 3 different strategies to tackle this problem.", "CREATE_NEW_PROBLEM", False),
        ("I want to define a new problem related to traffic congestion", "CREATE_NEW_PROBLEM", False),

        # --- CREATE NEW PROPOSAL ---
        ("I want to create a new proposal to solve the parking issue problem", "CREATE_NEW_PROPOSAL", False),

        # --- CREATE_NEW_SCENARIO ---
        ("Create a new scenario increasing parking capacity of 200 units", "CREATE_NEW_SCENARIO", False),
        ("Modify simA to increase parking spaces by 50", "CREATE_NEW_SCENARIO", False),

        # --- CONTEXT_MANAGEMENT ---
        ("Please, activate the first problem", "CONTEXT_MANAGEMENT", False),
        ("I want to focus on the fist two scenarios", "CONTEXT_MANAGEMENT", False),
        ("Remove simA from the context", "CONTEXT_MANAGEMENT", False),
        ("I am no longer interested in simA, let's focus on simB", "CONTEXT_MANAGEMENT", False),

        # --- INVALID (totally unclear) ---
        ("Do the thing for me", "INVALID", True),
        ("Blah blah blah", "INVALID", True),

        # --- INVALID (clear but unrelated to scenarios) ---
        ("What is the French Revolution?", "INVALID", True),
        ("Tell me about the weather in Paris", "INVALID", True),
    ],
)

def test_intent_classification(empty_state: AgentState, message, expected_intent, should_raise):
    # Copy base state safely
    state = replace(empty_state)

    # Set variables
    state.add_user_message(message)

    # Run nodes
    state = intent_node(state)
    
    assert state.cognitive.next_action == expected_intent
