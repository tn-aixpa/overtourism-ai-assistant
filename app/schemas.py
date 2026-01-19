from pydantic import BaseModel
from typing import Optional, Dict, Any



class AgentRequest(BaseModel):
    user_message: str
    sim_ids: list[str] = []
    simulation_data: Dict[str, Any] | None = None
    simulation_data_loaded_at: str | None = None
    pending_inputs: Dict[str, Any] = {}
    missing_inputs: list[str] = []
    awaiting_confirmation: bool = False
    running_simulation: bool = False
    next_action: str | None = None
    response: str = ""

    class Config:
        extra = "allow"


class AgentResponse(BaseModel):
    action: str | None
    response: str
    blocked: bool | None = None
    state: Dict[str, Any] | None = None

    class Config:
        extra = "allow"