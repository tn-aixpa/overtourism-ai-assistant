# app/api/routes.py
from fastapi import APIRouter
from app.schemas import AgentRequest, AgentResponse
from app.agent.state import AgentState
from app.services.agent_service import agent_app  # or however you import it

router = APIRouter()


@router.post("/agent", response_model=AgentResponse)
async def run_agent_endpoint(request: AgentRequest):
    """
    Endpoint to send a user message and simulation data to the agent.
    Preserves all fields including simulation_data.
    """

    # Convert Pydantic model to AgentState dataclass
    agent_state = AgentState(
        user_message=request.user_message,
        sim_ids=request.sim_ids,
        running_simulation=request.running_simulation,

        # 🔹 Preserve incoming simulation data and timestamp
        simulation_data=request.simulation_data or {},
        simulation_data_loaded_at=request.simulation_data_loaded_at,

        pending_inputs=request.pending_inputs or {},
        missing_inputs=request.missing_inputs or [],
        awaiting_confirmation=request.awaiting_confirmation or False,

        next_action=None,
        response="",
    )

    # Optional debug prints
    print("=== AgentState.simulation_data keys ===")
    print(list(agent_state.simulation_data.keys()) if agent_state.simulation_data else None)

    # Call the agent
    final_state = agent_app.invoke(agent_state)

    print("=== FINAL STATE RETURNED FROM AGENT ===")
    print(final_state)

    # Return response
    return AgentResponse(
        action=final_state.get("next_action"),
        response=final_state.get("response"),
        blocked=final_state.get("blocked"),
        state=final_state,  # optional full agent state
    )
