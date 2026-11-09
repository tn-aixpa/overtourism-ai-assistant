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
    - "pdf-report": runs report_generation and returns {"report": {...}}, a
      localized structured document the frontend renders and prints to PDF
      (shape in app.utils.report_document). `current_context` decides the
      content, most specific entity first: scenarios -> detailed scenario
      report with plots; else proposals -> the proposals and their scenarios;
      else problems -> the problems with their proposals and scenarios; empty
      or omitted -> every problem of the territory. `user_lang` selects the
      report language. No "temp" support.

    `steps` is currently unused by the route (each key hardcodes its own
    step sequence) and is reserved for a future explicit/arbitrary
    pipeline.
    """

    key: Literal["summary", "pdf-report"]
    steps: list[ToolStep] = Field(default_factory=list)
    user_lang: Literal["Italian", "English"] = "Italian"
    # Values are normally id lists (e.g. "scenarios": ["id1", "id2"]), but
    # "temp" (only meaningful for key == "summary") holds a nested
    # {"creation_session": ..., "evaluation_id": ...} dict — see
    # execute_get_context_details — so this can't be narrowed to
    # Dict[str, List[str]].
    current_context: Optional[Dict[str, Any]] = None
    stop_on_error: bool = True


# ---------------------------------------------------------------------------
# Visual page context (integrated mode)
# ---------------------------------------------------------------------------
# A snapshot of the Angular page the user is looking at, sent by the frontend
# on /agent/init and on every route navigation (/agent/context). It is
# UNTRUSTED input and remains separate from business context
# (AgentState.cognitive.current_context), except scenario_id may seed an empty
# scenario context. See docs/integrated-page-context.md.
#
# Limits: structural limits (payload bytes, element/option/row/column counts)
# REJECT the snapshot; per-string length limits TRUNCATE the string, because a
# user typing a long text into a textarea must not make the whole snapshot
# (and with it the assistant's awareness of the page) fail.
import os
import re
from datetime import date, datetime
from typing import Annotated, Union

from pydantic import BeforeValidator, field_validator


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


PAGE_CONTEXT_SCHEMA_MAJOR = "1"
PAGE_CONTEXT_MAX_BYTES = _env_int("PAGE_CONTEXT_MAX_BYTES", 64 * 1024)
PAGE_CONTEXT_MAX_ELEMENTS = _env_int("PAGE_CONTEXT_MAX_ELEMENTS", 150)
PAGE_CONTEXT_MAX_OPTIONS = 50
PAGE_CONTEXT_MAX_TABLE_ROWS = 25
PAGE_CONTEXT_MAX_TABLE_COLUMNS = 20
PAGE_CONTEXT_MAX_TEXT = 1000  # value / description of an element or page
PAGE_CONTEXT_MAX_SHORT_TEXT = 200  # id, label, option, table cell, title
PAGE_CONTEXT_MAX_ROUTE = 512
PAGE_CONTEXT_MAX_REVISION = 2**53 - 1  # largest integer a JS client can send

# ASCII control characters except tab/newline are never meaningful in UI text.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRUNCATION_MARK = "…[truncated]"


def _clip_text(value: str, limit: int) -> str:
    value = _CONTROL_CHARS.sub("", value)
    if len(value) > limit:
        return value[:limit] + _TRUNCATION_MARK
    return value


def _clipped(limit: int):
    def _validate(value):
        return _clip_text(value, limit) if isinstance(value, str) else value

    return BeforeValidator(_validate)


ShortText = Annotated[str, _clipped(PAGE_CONTEXT_MAX_SHORT_TEXT)]
LongText = Annotated[str, _clipped(PAGE_CONTEXT_MAX_TEXT)]
Scalar = Annotated[
    Union[str, int, float, bool, None], _clipped(PAGE_CONTEXT_MAX_TEXT)
]
CellScalar = Annotated[
    Union[str, int, float, bool, None], _clipped(PAGE_CONTEXT_MAX_SHORT_TEXT)
]

PageElementType = Literal[
    "textbox",
    "textarea",
    "number",
    "date",
    "checkbox",
    "radio",
    "switch",
    "dropdown",
    "multiselect",
    "button",
    "link",
    "tab",
    "heading",
    "text",
    "table",
    "list",
    "chart",
    "image",
    "other",  # escape hatch for widgets the contract does not name yet
]


class PageElement(BaseModel):
    """One UI element. Unknown fields are dropped, so a newer frontend that
    adds fields within the same major schema_version never breaks the call
    and extra data never reaches the LLM."""

    model_config = ConfigDict(extra="ignore")

    id: ShortText
    type: PageElementType
    label: Optional[ShortText] = None
    param_name: Optional[ShortText] = None
    value: Scalar = None  # text typed in, checkbox/switch state, number, ...
    selected: Optional[
        Union[ShortText, Annotated[List[ShortText], Field(max_length=50)]]
    ] = None
    options: Optional[
        Annotated[List[ShortText], Field(max_length=PAGE_CONTEXT_MAX_OPTIONS)]
    ] = None
    visible: bool = True
    enabled: bool = True
    required: Optional[bool] = None
    error: Optional[ShortText] = None  # validation message the UI shows
    group: Optional[ShortText] = None  # form section / card the element is in
    # type == "table": a bounded sample of what is on screen.
    columns: Optional[
        Annotated[List[ShortText], Field(max_length=PAGE_CONTEXT_MAX_TABLE_COLUMNS)]
    ] = None
    rows: Optional[
        Annotated[
            List[List[CellScalar]], Field(max_length=PAGE_CONTEXT_MAX_TABLE_ROWS)
        ]
    ] = None
    row_count: Optional[int] = Field(default=None, ge=0)  # total, if rows is a sample
    # type == "chart": what is plotted, without the plotted data.
    chart_type: Optional[ShortText] = None
    chart_subsystem: Optional[ShortText] = None
    index_id: Optional[ShortText] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    granularity: Optional[ShortText] = None

    @field_validator("rows")
    @classmethod
    def _bounded_row_width(cls, rows):
        if rows and any(len(r) > PAGE_CONTEXT_MAX_TABLE_COLUMNS for r in rows):
            raise ValueError(
                f"table rows may have at most {PAGE_CONTEXT_MAX_TABLE_COLUMNS} cells"
            )
        return rows


class PageContextEntities(BaseModel):
    """Bounded identifiers and selections supplied by the rendered page."""

    model_config = ConfigDict(extra="ignore")

    territory: Optional[ShortText] = None
    scenario_id: Optional[ShortText] = None
    proposal_id: Optional[ShortText] = None
    problem_id: Optional[ShortText] = None
    active_tab: Optional[ShortText] = None
    index_id: Optional[ShortText] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    granularity: Optional[ShortText] = None
    selected_territories: Optional[
        Annotated[List[ShortText], Field(max_length=20)]
    ] = None


class PageContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    captured_at: Optional[datetime] = None
    route: Annotated[str, Field(min_length=1), _clipped(PAGE_CONTEXT_MAX_ROUTE)]
    page_title: Optional[ShortText] = None
    page_description: Optional[LongText] = None
    # Client-side, monotonically increasing per session (a persisted counter or
    # epoch milliseconds). Lets the server drop an older snapshot that arrives
    # after a newer one. Optional: without it, last write wins.
    revision: Optional[int] = Field(
        default=None, ge=0, le=PAGE_CONTEXT_MAX_REVISION
    )
    entities: Optional[PageContextEntities] = None
    elements: List[PageElement] = Field(
        default_factory=list, max_length=PAGE_CONTEXT_MAX_ELEMENTS
    )

    @field_validator("schema_version")
    @classmethod
    def _supported_major_version(cls, v: str) -> str:
        if not re.fullmatch(rf"{PAGE_CONTEXT_SCHEMA_MAJOR}\.\d{{1,3}}", v):
            raise ValueError(
                f"unsupported schema_version {v!r}; "
                f"supported: {PAGE_CONTEXT_SCHEMA_MAJOR}.x"
            )
        return v
