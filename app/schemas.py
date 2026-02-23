from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional



class ConversationMessage(BaseModel):
    role: str
    content: str


class CognitivePayload(BaseModel):
    next_action: Optional[str] = None

    problem_id: str = ""
    scenario_ids: List[str] = Field(default_factory=list)

    selected_roles: List[str] = Field(default_factory=list)
    expert_answers: Dict[str, Any] = Field(default_factory=dict)

    data: Dict[str, Any] = Field(default_factory=dict)

class AgentRequest(BaseModel):
    conversation: List[ConversationMessage] = Field(default_factory=list)
    session_id: str = "000"
    next_action: Optional[str] = None
    cognitive: Optional[CognitivePayload] = None

    class Config:
        extra = "allow"
        
class AgentResponse(BaseModel):
    action: Optional[str] = None
    response: Optional[str] = None
    blocked: Optional[bool] = None
    cognitive: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"