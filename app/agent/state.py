import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import StrEnum, Enum
import json

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 5

@dataclass
class ConversationMessage:
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    generated_by: Optional[str] = None
    vote: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class ConversationBuffer:
    messages: List[ConversationMessage] = field(default_factory=list)
    max_window_size: int = MAX_CONTEXT_WINDOW

    def add_message(self, message: ConversationMessage):
        self.messages.append(message)

    def get_last_n(self, n: Optional[int] = None) -> List[ConversationMessage]:
        n = n or self.max_window_size
        return self.messages[-n:]

    def get_context_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        """Returns last N messages formatted for LLM reasoning."""
        msgs = self.get_last_n(n)
        return [{"role": m.role, "content": m.content} for m in msgs]


@dataclass
class TraceStep:
    step_type: str
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
            self.steps = self.steps[-self.max_trace_size:]

    def get_last_n(self, n: Optional[int] = None) -> List[TraceStep]:
        n = n or self.max_trace_size
        return self.steps[-n:]


@dataclass
class CognitiveState:
    generation_pipeline: List[str] = field(default_factory=list)

    current_context: Dict[str, Any] = field(
        default_factory=lambda: {"problems": [], "proposals": [], "scenarios": []}
    )
    retrieved_context: Dict[str, Any] = field(default_factory=dict)

    trace: TraceBuffer = field(default_factory=TraceBuffer)

    error_code: str = ""
    error_node: str = ""
    error_details: str = ""

    messages_to_include: List[str] = field(default_factory=list)
    additional_output_information: List[str] = field(default_factory=list)

    known_tools: List[str] = field(default_factory=list)
    enabled_tools: List[str] = field(default_factory=list)
    selected_tool: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)

    tool_plan: List[Dict[str, Any]] = field(default_factory=list)
    tool_plan_index: int = 0

    tool_result: Optional[Dict[str, Any]] = None
    tool_results: Dict[str, Any] = field(default_factory=dict)
    tool_confirmation_needed: bool = False
    # Set to True right after the user confirms a pending creation tool, so that
    # tool_executor knows to actually run it instead of pausing again.
    tool_confirmed: bool = False

    def _add_trace(self, step_type: str, node: str, data: Optional[Dict[str, Any]] = None):
        self.trace.add_step(TraceStep(step_type=step_type, node=node, data=data))


@dataclass
class AgentState:
    # Interface layer
    conversation: ConversationBuffer = field(default_factory=ConversationBuffer)
    chart_data: Optional[dict[str, Any]] = None
    sliders_data: Optional[dict[str, Any]] = None

    # Orchestration
    session_id: str = ""
    user_lang: str = "English"
    integrated_mode: bool = False

    class Workflow(StrEnum):
        INTENT = "intent"
        PROBLEM_CREATION = "new_problem"
        PROPOSAL_CREATION = "new_proposal"
        SCENARIO_CREATION = "new_scenario"
        INTERACTION = "interaction"

    active_workflow: Optional["AgentState.Workflow"] = None
    suspended_workflow: Optional["AgentState.Workflow"] = None
    suspended_waiting_for: Optional["AgentState.WaitingFor"] = None

    class WaitingFor(StrEnum):
        PROBLEM_INPUT = "PROBLEM_INPUT"
        PROBLEM_CONFIRMATION = "PROBLEM_CONFIRMATION"
        PROPOSAL_INPUT = "PROPOSAL_INPUT"
        PROPOSAL_CONFIRMATION = "PROPOSAL_CONFIRMATION"
        SCENARIO_INPUT = "SCENARIO_INPUT"
        SCENARIO_CONFIRMATION = "SCENARIO_CONFIRMATION"
        CONTEXT_INPUT = "CONTEXT_INPUT"

    waiting_for: Optional["AgentState.WaitingFor"] = None
    user_input: Optional[str] = None

    # Cognitive layer
    cognitive: CognitiveState = field(default_factory=CognitiveState)

    @property
    def last_node(self):
        if not self.cognitive.trace.steps:
            return None
        return self.cognitive.trace.steps[-1].node

    def add_trace(self, step_type: str, node: str | None = None, data: Optional[Dict[str, Any]] = None):
        self.cognitive._add_trace(step_type=step_type, node=node, data=data)

    def add_user_message(self, content: str):
        self.conversation.add_message(ConversationMessage(role="user", content=content))

    def add_assistant_message(self, content: str):
        from app.utils.llm import BACKUP_PROVIDER, LOCAL_MODEL, SMARTLAB_MODEL

        pipeline = self.cognitive.generation_pipeline

        def _provider_label(model_name: str) -> str:
            if model_name.startswith("claude"):
                return "anthropic"
            if model_name == SMARTLAB_MODEL:
                return f"smartlab-{SMARTLAB_MODEL}"
            if model_name == LOCAL_MODEL:
                return f"ollama-{LOCAL_MODEL}"
            return f"{BACKUP_PROVIDER}-{model_name}"

        labels = {_provider_label(m) for m in pipeline}

        if len(labels) == 0:
            generated_by = "unknown"
        elif len(labels) == 1:
            generated_by = labels.pop()
        else:
            generated_by = "mixed"

        self.conversation.add_message(
            ConversationMessage(role="assistant", content=content, generated_by=generated_by)
        )

    def get_last_user_message(self):
        for msg in reversed(self.conversation.messages):
            if msg.role == "user":
                return msg
        return None

    def get_last_message(self):
        if self.conversation.messages:
            return self.conversation.messages[-1]
        return None

    def get_reasoning_context(self, n: Optional[int] = DEFAULT_REASONING_CONTEXT_SIZE):
        return self.conversation.get_context_window(n)

    def _serialize(self, obj: Any):
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
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {f.name: self._serialize(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return repr(obj)

    def dump_to_file(self, filepath: str):
        import os
        os.makedirs("logs", exist_ok=True)
        serialized = self._serialize(self.__dict__)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)

    def reset_state(
        self,
        reset_new_problem=False,
        reset_new_proposal=False,
        reset_new_scenario=False,
        reset_errors=False,
        reset_chart=True,
    ):
        self.waiting_for = None
        self.user_input = None
        self.sliders_data = None

        self.cognitive.generation_pipeline = []
        self.cognitive.tool_plan = []
        self.cognitive.tool_plan_index = 0
        self.cognitive.tool_results = {}
        self.cognitive.selected_tool = None
        self.cognitive.tool_arguments = {}
        self.cognitive.tool_result = None
        self.cognitive.tool_confirmation_needed = False
        self.cognitive.tool_confirmed = False

        if reset_chart:
            self.chart_data = None

        if reset_new_problem:
            self.cognitive.problem_info_extracted = {}
            self.cognitive.extracted_all_problem = False

        if reset_new_proposal:
            self.cognitive.proposal_info_extracted = {}
            self.cognitive.extracted_all_proposal = False

        if reset_new_scenario:
            self.cognitive.extracted_all_scenario = False
            self.cognitive.scenarios_to_generate = []
            self.cognitive.scenario_validation_errors = ""

        if reset_errors:
            self.cognitive.error_code = ""
            self.cognitive.error_node = ""
            self.cognitive.error_details = ""
            self.cognitive.messages_to_include = []
