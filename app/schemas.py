from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal, Optional, List, Dict


class AgentResponse(BaseModel):
    session_id: str
    response: Optional[str] = None
    agent_type: str
    # List of UIAction-shaped dicts: {"type": "SHOW_WIDGET" | "NAVIGATE" | "SHOW_TOAST", "payload": {...}}.
    # Matches the frontend's UIAction[] (see chat.model.ts / ChatbotActionTranslatorService).
    assistant_action_data: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(extra="allow")


class ToolStep(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class RunSelectedToolsRequest(BaseModel):
    """Body for POST /agent/tool.

    `key` selects the pipeline (see `run_selected_tools` in api/routes.py
    for the step sequence each one runs against a shared, throwaway
    AgentState — no session_id, nothing persisted):

    - "summary": runs get_context_details -> summary_generation.
      `current_context` seeds that state's current_context so the steps
      don't need to re-resolve it. It normally holds id lists, e.g.
      {"scenarios": ["id1", "id2"]}. It may also carry a "temp" entry —
      {"creation_session": ..., "evaluation_id": ...} — identifying a
      temporary, not-yet-saved scenario/evaluation created via a creation
      session (see create_temp_scenario); when present,
      get_context_details fetches that temporary evaluation data directly
      and folds its resolved scenario id into current_context["scenarios"].
    - "pdf-report": runs get_context_details -> report_generation, seeded
      the same way via `current_context` (without "temp" support).

    `steps` is currently unused by the route (each key hardcodes its own
    step sequence) and is reserved for a future explicit/arbitrary
    pipeline.
    """

    key: Literal["summary", "pdf-report"]
    steps: list[ToolStep] = Field(default_factory=list)
    # Values are normally id lists (e.g. "scenarios": ["id1", "id2"]), but
    # "temp" (only meaningful for key == "summary") holds a nested
    # {"creation_session": ..., "evaluation_id": ...} dict — see
    # execute_get_context_details — so this can't be narrowed to
    # Dict[str, List[str]].
    current_context: Optional[Dict[str, Any]] = None
    stop_on_error: bool = True
