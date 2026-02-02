from app.agent.graph import app as agent_app
from app.agent.state import AgentState


def run_agent(request) -> AgentState:
    initial_state = AgentState(
        user_message=request.user_message,
        _id=request.scenario_ids,
        running_scenario=request.running_scenario,

        # 🔹 Preserve incoming data and timestamp
        data=request.data,
        data_loaded_at=request.data_loaded_at,

        current_input=request.current_input or {},
        awaiting_confirmation=request.awaiting_confirmation or False,

        next_action=None,
        response="",
    )

    return agent_app.invoke(initial_state)