import pytest
from app.agent.graph import app
from app.agent.state import AgentState, CognitiveState, ConversationBuffer
from tests.utils.agent_runner import AgentTestRunner


@pytest.fixture
def empty_state():
    return AgentState(
        conversation=ConversationBuffer(),
        session_id="",
        user_lang="English",
        cognitive=CognitiveState()
    )

@pytest.fixture
def agent(empty_state):
    return AgentTestRunner(app, empty_state)