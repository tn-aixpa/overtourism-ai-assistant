from app.agent.graph import app as agent_app
from app.agent.state import AgentState
from datetime import datetime


def run_agent(request) -> AgentState:
    initial_state: AgentState = {
        "user_message": request.user_message,

        "sim1_id": request.sim1_id,
        "sim2_id": request.sim2_id,

        "analysis_mode": None,

        "simulation_data": None,
        "simulation_data_loaded_at": None,

        "pending_inputs": {},
        "missing_inputs": [],
        "awaiting_confirmation": False,
        "running_simulation": request.running_simulation,

        "next_action": None,
        "response": "",
    }

    return agent_app.invoke(initial_state)
