
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import StrEnum, Enum
import json

from app.config import MAX_CONTEXT_WINDOW, DEFAULT_REASONING_CONTEXT_SIZE, ALLOWED_OPERATIONS

@dataclass
class ConversationMessage:
    role: str  # "user" | "assistant"
    content_localized: str  # localized user-facing content(e.g. Italian)
    content_en: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ConversationBuffer:
    messages: List[ConversationMessage] = field(default_factory=list)
    max_window_size: int = MAX_CONTEXT_WINDOW  # configurable context window

    def add_message(self, message: ConversationMessage):
        self.messages.append(message)

    def get_last_n(self, n: Optional[int] = None) -> List[ConversationMessage]:
        n = n or self.max_window_size
        return self.messages[-n:]

    def get_context_window_en(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Returns last N messages formatted for LLM reasoning (English only).
        """
        msgs = self.get_last_n(n)
        return [{"role": m.role, "content": m.content_en} for m in msgs]

    def get_context_window_localized(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Returns last N messages in user language (UI use only).
        """
        msgs = self.get_last_n(n)
        return [{"role": m.role, "content": m.content_localized} for m in msgs]

@dataclass
class TraceStep:
    step_type: str  # e.g., "tool_call", "node_execution"
    node: str | None = None
    data: Optional[Dict[str, Any]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class TraceBuffer:
    steps: List[TraceStep] = field(default_factory=list)
    max_trace_size: int = 1000

    def add_step(self, step: TraceStep):
        self.steps.append(step)
        if len(self.steps) > self.max_trace_size:
            # remove oldest steps to keep buffer size
            self.steps = self.steps[-self.max_trace_size:]

    def get_last_n(self, n: Optional[int] = None) -> List[TraceStep]:
        n = n or self.max_trace_size
        return self.steps[-n:]

@dataclass
class CognitiveState:
    # Canonical reasoning language: ENGLISH

    # Routing
    next_action: Optional[str] = None

    # Operations
    allowed_operations = ALLOWED_OPERATIONS

    # Listing
    elements_to_list: List[str] = field(default_factory=list)
    filter_list_by: str = None
    partial_list: Dict[str, Any] = field(default_factory=dict)

    # Active context
    active_context_type: str = "" #problem, proposal, scenario
    active_context: List[str] = field(default_factory=list)
    previous_context: List[str] = field(default_factory=list)

    # Problem context
    problem_info_to_extract: Dict[str, Any] = field(default_factory=dict)
    extracted_problem_info: Dict[str, Any] = field(default_factory=dict)
    extracted_all_problem: bool = False

    # Scenario context
    scenario_info_to_extract: Dict[str, Any] = field(default_factory=dict)
    extracted_all_scenario: bool = False

    # Execution state
    scenarios_to_generate: List[Dict[str, Any]] = field(default_factory=list)
    validation_errors: str = ""

    # Expert reasoning
    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)

    # Data layer
    available_entries: Dict[str, Any] = field(default_factory=dict)
    context_data: Dict[str, Any] = field(default_factory=dict)
    editable_indexes: Dict[str, Any] = field(default_factory=dict)

    # Tracing
    trace: TraceBuffer = field(default_factory=TraceBuffer)

    # Error handling
    error_code: str = ""
    error_node: str = ""
    error_details: str = ""

    # Messages to include in response
    messages_to_include: List[str] = field(default_factory=list)
    additional_output_information: Dict[str, Any] = field(default_factory=dict)

    def _add_trace(self, step_type: str, node: str, data: Optional[Dict[str, Any]] = None):
        self.trace.add_step(TraceStep(step_type=step_type, node=node, data=data))

@dataclass
class AgentState:
    # Interface layer (Localized language only)
    conversation: ConversationBuffer = field(default_factory=ConversationBuffer)

    # Orchestration Layer (English only)
    session_id: str = ""
    user_lang: str = "English"

    # Workflow orchestration
    class Workflow(StrEnum):
        INTENT = "intent"
        PROBLEM = "problem"
        SCENARIO_EXTRACTION = "scenario_extraction"
        INTERACTION = "interaction"
        SCENARIO_RUNNER = "scenario_runner"

    resume_nome: Dict[str, str] = field(default_factory=dict)
    active_workflow: Optional["AgentState.Workflow"] = None

    class WaitingFor(StrEnum):
        PROBLEM_INPUT = "PROBLEM_INPUT"
        PROBLEM_CONFIRMATION = "PROBLEM_CONFIRMATION"
        SCENARIO_PREFERENCE = "SCENARIO_PREFERENCE"
        SCENARIO_INPUT = "SCENARIO_INPUT"
        SCENARIO_CONFIRMATION = "SCENARIO_CONFIRMATION"
        CONTEXT_INPUT = "CONTEXT_INPUT"

    waiting_for: Optional["AgentState.WaitingFor"] = None
    # Raw user input used to resume from WAIT_USER_INPUT.
    # (When using the HTTP API, this is populated only when `waiting_for` is set.)
    user_input: Optional[str] = None

    # Cognitive Layer (English only)
    cognitive: CognitiveState = field(default_factory=CognitiveState)

    @property
    def last_node(self):
        if not self.cognitive.trace.steps:
            return None
        return self.cognitive.trace.steps[-1].node

    # ---- Methods ----

    def add_trace(self, step_type: str, node: str | None = None, data: Optional[Dict[str, Any]] = None):
        self.cognitive._add_trace(step_type=step_type, node=node, data=data)

    def add_user_message(self, localized: str, translated_en: str):
        self.conversation.add_message(
            ConversationMessage(
                role="user",
                content_localized=localized,
                content_en=translated_en,
            )
        )

    def add_assistant_message(self, localized: str, translated_en: str):
        self.conversation.add_message(
            ConversationMessage(
                role="assistant",
                content_localized=localized,
                content_en=translated_en,
            )
        )

    def get_last_user_message(self):
        for msg in reversed(self.conversation.messages):
            if msg.role == "user":
                return msg
        return None
    
    def get_last_message(self):
        if len(self.conversation.messages) > 0:
            return self.conversation.messages[-1]
        return None

    def get_reasoning_context(self, n: Optional[int] = DEFAULT_REASONING_CONTEXT_SIZE):
        return self.conversation.get_context_window_en(n)

    def get_ui_context(self, n: Optional[int] = DEFAULT_REASONING_CONTEXT_SIZE):
        return self.conversation.get_context_window_localized(n)
    
    def get_active_context_string(self):
        context_type = self.cognitive.active_context_type
        contexts = self.cognitive.active_context or []

        if context_type:
            plural = "s" if len(contexts) > 1 else ""
            return f"{context_type}{plural} {', '.join(contexts)}"
        
        return ""
    
    # -------------------------
    # Dump state
    # -------------------------

    def _serialize(self, obj: Any):
        """Recursively serialize non-JSON-safe objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()

        if isinstance(obj, Enum):
            return obj.value

        if isinstance(obj, set):           # <-- add this
            return sorted(self._serialize(i) for i in obj)

        if isinstance(obj, list):
            return [self._serialize(i) for i in obj]

        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}

        return obj

    def dump_to_file(self, filepath: str):
        """
        Dump the full AgentState to a JSON file.
        Useful for debugging, replay, or audit logs.
        """
        raw_dict = asdict(self)
        serialized = self._serialize(raw_dict)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)

    def save(self):
        # For debugging, replace later with proper saving
        with open("logs/traceback.log", "a+") as f:
            f.write(f"Saved state for session_id={self.session_id}, last node={self.last_node}\n")
            for trace in self.cognitive.trace.steps:
                f.write(f"  - {trace.timestamp} | {trace.step_type} | {trace.node} | {str(trace.data)}\n")
