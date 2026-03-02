import pytest
from app.agent.state import AgentState, CognitiveState, ConversationBuffer


@pytest.fixture
def empty_state():
    return AgentState(
        conversation=ConversationBuffer(),
        session_id="",
        user_lang="English",
        cognitive=CognitiveState()
    )