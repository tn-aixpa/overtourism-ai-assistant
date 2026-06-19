from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, List, Optional

class ConversationMessage(BaseModel):
    role: str
    content: str

class AgentRequest(BaseModel):
    conversation: List[ConversationMessage] = Field(default_factory=list)
    session_id: str = "000"

    model_config = ConfigDict(extra="allow")
        
class AgentResponse(BaseModel):
    session_id: str
    response: Optional[str] = None
    chart_data: Optional[dict[str, Any]] = None  # Plotly figure JSON or None
    sliders_data: Optional[dict[str, Any]] = None  # Slider controls parsed from HTML pages

    model_config = ConfigDict(extra="allow")