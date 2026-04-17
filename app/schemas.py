from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, List, Optional

class ConversationMessage(BaseModel):
    role: str
    content: str


class CognitivePayload(BaseModel):
    next_action: Optional[str] = None

    active_context_type: str = ""
    active_context: List[str] = Field(default_factory=list)

    selected_roles: List[str] = Field(default_factory=list)

    data: Dict[str, Any] = Field(default_factory=dict)

class AgentRequest(BaseModel):
    conversation: List[ConversationMessage] = Field(default_factory=list)
    session_id: str = "000"
    next_action: Optional[str] = None
    cognitive: Optional[CognitivePayload] = None

    model_config = ConfigDict(extra="allow")
        
class AgentResponse(BaseModel):
    response: Optional[str] = None
    session_id: str
    active_context: str
    chart_data: Optional[dict[str, Any]] = None  # Plotly figure JSON or None
    sliders_data: Optional[dict[str, Any]] = None  # Slider controls parsed from HTML pages

    model_config = ConfigDict(extra="allow")