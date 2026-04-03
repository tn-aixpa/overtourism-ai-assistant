from app.agent.graph import app as agent_app
from app.agent.state import AgentState, ConversationMessage


def run_agent(request) -> AgentState:
    initial_state = AgentState(
        conversation=ConversationMessage(
            role="user",
            content=request.message if request.message else "",
        ),
        session_id=request.session_id,
        user_lang=request.user_lang,

        next_action=None,
    )

    return agent_app.invoke(initial_state)