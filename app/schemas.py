from pydantic import BaseModel, ConfigDict
from typing import Any, Optional


class AgentResponse(BaseModel):
    session_id: str
    response: Optional[str] = None
    assistant_action_data: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")
