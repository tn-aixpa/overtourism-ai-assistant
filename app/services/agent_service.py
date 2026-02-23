from datetime import datetime
from app.agent.graph import app as agent_app
from app.agent.state import AgentState, ConversationMessage


def run_agent(request) -> AgentState:
    initial_state = AgentState(
        conversation=ConversationMessage(
            role="user",
            content=request.message if request.message else "",
            timestamp=datetime.now()
        ),
        _id=request.cognitive.scenario_ids,

        # 🔹 Preserve incoming data and timestamp
        data=request.cognitive.data,

        next_action=None,
    )

    return agent_app.invoke(initial_state)