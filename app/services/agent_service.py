from app.agent.graph import app as agent_app
from app.agent.state import AgentState


def run_agent(request) -> AgentState:
    initial_state = AgentState(
        user_message=request.user_message,
        _id=request.sim_ids,
        running_simulation=request.running_simulation,

        # 🔹 Preserve incoming simulation_data and timestamp
        simulation_data=request.simulation_data,
        simulation_data_loaded_at=request.simulation_data_loaded_at,

        pending_inputs=request.pending_inputs or {},
        missing_inputs=request.missing_inputs or [],
        awaiting_confirmation=request.awaiting_confirmation or False,

        next_action=None,
        response="",
    )

    return agent_app.invoke(initial_state)