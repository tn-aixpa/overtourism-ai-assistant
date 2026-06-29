from pydantic import BaseModel, ConfigDict
from typing import Any, Optional


class AgentResponse(BaseModel):
    session_id: str
    response: Optional[str] = None
    chart_data: Optional[dict[str, Any]] = None
    sliders_data: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")
