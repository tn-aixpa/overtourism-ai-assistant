from pydantic import BaseModel
from typing import Optional, Dict, Any


class AgentRequest(BaseModel):
    user_message: str
    sim1_id: Optional[str] = None
    sim2_id: Optional[str] = None
    running_simulation: bool = False


class AgentResponse(BaseModel):
    action: Optional[str]
    response: str
    state: Optional[Dict[str, Any]] = None  # optional for debugging
