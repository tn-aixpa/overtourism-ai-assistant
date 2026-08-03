from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional, List, Dict


class AgentResponse(BaseModel):
    session_id: str
    response: Optional[str] = None
    # List of UIAction-shaped dicts: {"type": "SHOW_WIDGET" | "NAVIGATE" | "SHOW_TOAST", "payload": {...}}.
    # Matches the frontend's UIAction[] (see chat.model.ts / ChatbotActionTranslatorService).
    assistant_action_data: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(extra="allow")


class ToolStep(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class RunSelectedToolsRequest(BaseModel):
    """Body for POST /agent/tool.

    `key` selects the pipeline flavor (e.g. "summary"). `steps` is the
    explicit, ordered list of tools to run against a shared, throwaway
    AgentState (no session_id, nothing persisted). For key == "summary",
    `scenario_ids` are pre-seeded into that state's current_context so the
    steps (e.g. summary_generation, optionally preceded by
    get_context_details) don't need to re-resolve them.
    """

    key: str
    steps: list[ToolStep] = Field(default_factory=list)
    scenario_ids: list[str] = Field(default_factory=list)
    stop_on_error: bool = True
