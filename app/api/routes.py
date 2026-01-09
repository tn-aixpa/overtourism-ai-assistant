from fastapi import APIRouter
from app.schemas import AgentRequest, AgentResponse
from app.services.agent_service import run_agent

router = APIRouter()


@router.post("/agent", response_model=AgentResponse)
def run_agent_endpoint(request: AgentRequest):
    final_state = run_agent(request)

    return AgentResponse(
        action=final_state.get("next_action"),
        response=final_state.get("response"),
        blocked=final_state.get("blocked"),
        state=final_state,  # optional
    )
