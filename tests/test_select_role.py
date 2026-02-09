# test_select_role_integration.py
import pytest

from app.agent.nodes.select_role import select_role
from app.agent.state import AgentState

# -----------------------------
# Single-role tests (6)
# -----------------------------

@pytest.mark.parametrize(
    "question, expected_role",
    [
        # Data Analyst
        ("What is the peak visitor count?", "Data Analyst"),
        ("Show me the monthly revenue data.", "Data Analyst"),

        # Environment Specialist
        ("What are the environmental impacts of increasing parking in the analyzed area?", "Environment Specialist"),
        ("How would this affect sustainability?", "Environment Specialist"),

        # Urban Planner
        ("How should we redesign traffic flow?", "Urban Planner"),
        ("What infrastructure changes are needed?", "Urban Planner"),
    ],
)
def test_single_roles(question, expected_role):
    state = AgentState(messages=[{"role": "user", "content": question}])
    new_state = select_role(state)

    # We assert the expected role is included in selected_roles
    assert expected_role in new_state.selected_roles
    # For single-role questions, ensure only one role is returned
    assert len(new_state.selected_roles) == 1

# -----------------------------
# Multi-role tests (2)
# -----------------------------

@pytest.mark.parametrize(
    "question",
    [
        ("Which of the proposed solutions minimizes costs while improving sustainability?"),

        ("Analyze the scenario and propose policies with environmental impacts and infrastructure changes."),
    ],
)
def test_multi_roles(question):
    state = AgentState(messages=[{"role": "user", "content": question}])
    new_state = select_role(state)

    # Must return multiple roles
    assert len(new_state.selected_roles) >= 2
