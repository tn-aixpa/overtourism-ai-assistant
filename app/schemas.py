from pydantic import BaseModel
from typing import Dict, Any



class AgentRequest(BaseModel):
    problem_id: str = ""
    scenario_ids: list[str] = []
    session_id: str = "000"

    messages: list[Dict[str, Any]] = []
    next_action: str | None = None   

    data: Dict[str, Any] | None = None
    data_loaded_at: str | None = None
    
    current_input: Dict[str, Any] = {}
    awaiting_confirmation: bool = False
    running_scenario: bool = False

    selected_roles: list[str] = []
    expert_answers: Dict[str, Any] | None = None


    class Config:
        extra = "allow"


class AgentResponse(BaseModel):
    action: str | None
    response: str | None = None
    blocked: bool | None = None
    state: Dict[str, Any] | None = None

    class Config:
        extra = "allow"
        