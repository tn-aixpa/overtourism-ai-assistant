
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import StrEnum, Enum
import json

from app.config import MAX_CONTEXT_WINDOW, DEFAULT_REASONING_CONTEXT_SIZE, ALLOWED_OPERATIONS
from app.utils.backend_integration_classes import (
    ProblemInfoSchema,
    ProblemInfo,
    ProposalInfoSchema,
    ProposalInfo,
    ScenarioInfoSchema,
    ScenarioInfo
)

@dataclass
class ConversationMessage:
    role: str  # "user" | "assistant"
    content: str
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

    def get_context_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Returns last N messages formatted for LLM reasoning (English only).
        """
        msgs = self.get_last_n(n)
        return [{"role": m.role, "content": m.content} for m in msgs]

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
    problem_info_to_extract = ProblemInfoSchema.default()
    problem_info_extracted: ProblemInfo = None
    extracted_all_problem: bool = False

    #Proposal context
    proposal_info_to_extract = ProposalInfoSchema.default()
    proposal_info_extracted: ProposalInfo = None
    extracted_all_proposal: bool = False

    # Scenario context
    scenario_info_to_extract = ScenarioInfoSchema.default()
    scenarios_to_generate: List[ScenarioInfo] = field(default_factory=list)
    extracted_all_scenario: bool = False
    scenario_validation_errors: str = ""

    # Expert reasoning
    selected_roles: List[str] = field(default_factory=list)

    # Data layer
    available_entries: Dict[str, Any] = field(default_factory=dict) #{"all_ids": ..., "ids_dict": ..., "connections_dict": ..., "names_dict": ...}
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
    additional_output_information: List[str] = field(default_factory=list)

    def _add_trace(self, step_type: str, node: str, data: Optional[Dict[str, Any]] = None):
        self.trace.add_step(TraceStep(step_type=step_type, node=node, data=data))

@dataclass
class AgentState:
    # Interface layer (Localized language only)
    conversation: ConversationBuffer = field(default_factory=ConversationBuffer)
    chart_data: Optional[dict[str, Any]] = None

    # Orchestration Layer (English only)
    session_id: str = ""
    user_lang: str = "English"

    # Workflow orchestration
    class Workflow(StrEnum):
        INTENT = "intent"
        PROBLEM_CREATION = "new_problem"
        PROPOSAL_CREATION = "new_proposal"
        SCENARIO_CREATION = "new_scenario"
        INTERACTION = "interaction"

    resume_nome: Dict[str, str] = field(default_factory=dict)
    active_workflow: Optional["AgentState.Workflow"] = None

    class WaitingFor(StrEnum):
        PROBLEM_INPUT = "PROBLEM_INPUT"
        PROBLEM_CONFIRMATION = "PROBLEM_CONFIRMATION"
        PROPOSAL_INPUT = "PROPOSAL_INPUT"
        PROPOSAL_CONFIRMATION = "PROPOSAL_CONFIRMATION"
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

    def add_user_message(self, content: str):
        self.conversation.add_message(
            ConversationMessage(
                role="user",
                content=content,
            )
        )

    def add_assistant_message(self, content: str):
        self.conversation.add_message(
            ConversationMessage(
                role="assistant",
                content=content,
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
        return self.conversation.get_context_window(n)
    
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

        if isinstance(obj, Exception):
            return str(obj)

        if isinstance(obj, set):
            return sorted(self._serialize(i) for i in obj)

        if isinstance(obj, list):
            return [self._serialize(i) for i in obj]

        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}

        # Handle any dataclass (FieldSpec, BaseSchema subclasses, etc.)
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {
                f.name: self._serialize(getattr(obj, f.name))
                for f in dataclasses.fields(obj)
            }

        # Safe fallback
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return repr(obj)

    def dump_to_file(self, filepath: str):
        """
        Dump the full AgentState to a JSON file.
        Useful for debugging, replay, or audit logs.
        """
        serialized = self._serialize(self.__dict__)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)

    def save(self):
        # For debugging, replace later with proper saving
        with open("logs/traceback.log", "a+") as f:
            f.write(f"Saved state for session_id={self.session_id}, last node={self.last_node}\n")
            for trace in self.cognitive.trace.steps:
                f.write(f"  - {trace.timestamp} | {trace.step_type} | {trace.node} | {str(trace.data)}\n")

    def reset_state(self, reset_errors=True, reset_context=True, reset_data=True):
        self.waiting_for = None
        self.user_input = None
        self.chart_data = None

        # Reset cognitive
        self.cognitive.elements_to_list = []
        self.cognitive.filter_list_by = ""
        self.cognitive.partial_list = {}
        self.cognitive.problem_info_extracted = {}
        self.cognitive.extracted_all_problem = False
        self.cognitive.extracted_all_scenario = False
        self.cognitive.scenarios_to_generate = []
        self.cognitive.scenario_validation_errors = ""
        self.cognitive.selected_roles = []

        if reset_errors:
            self.cognitive.error_code = ""
            self.cognitive.error_node = ""
            self.cognitive.error_details = ""
            self.cognitive.messages_to_include = []

        if reset_context:
            self.cognitive.active_context_type = ""
            self.cognitive.active_context = []
            self.cognitive.previous_context = []

        if reset_data:
            self.cognitive.context_data = {}
            self.cognitive.editable_indexes = {}
            self.cognitive.available_entries = {}

        return self
