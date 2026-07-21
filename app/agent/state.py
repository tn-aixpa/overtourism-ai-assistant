import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import StrEnum, Enum
import json

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 5
# Safety cap on Thought/Action/Observation cycles within a single turn, so a
# reasoner that never emits "finish" (e.g. stuck bouncing between two tools)
# cannot loop forever. See react_reasoner_node in nodes/reasoner.py.
DEFAULT_MAX_REACT_STEPS = 8


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
            self.steps = self.steps[-self.max_trace_size :]

    def get_last_n(self, n: Optional[int] = None) -> List[TraceStep]:
        n = n or self.max_trace_size
        return self.steps[-n:]


@dataclass
class ReActStep:
    """One Thought -> Action -> Observation cycle produced by the ReAct
    reasoner during a single turn.

    The scratchpad (a list of these) is the working memory of the loop: it
    is fed back into the reasoning prompt on every iteration so the model
    can decide its next action based on what it has already seen, and it is
    reset to empty at the start of every new user turn (see
    `initialize_tools`). It is NOT the same as `tool_results`, which is kept
    across the whole session as long-term memory.
    """

    thought: str = ""
    tool_name: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None
    # Key into cognitive.tool_results where the full observation is stored.
    observation_key: Optional[str] = None
    # Informational only (e.g. "awaiting_confirmation", "cancelled") — never
    # used for routing, just for tracing/debugging.
    status: Optional[str] = None


@dataclass
class CognitiveState:
    generation_pipeline: List[str] = field(default_factory=list)

    current_context: Dict[str, Any] = field(
        default_factory=lambda: {"problems": [], "proposals": [], "scenarios": []}
    )
    retrieved_context: Dict[str, Any] = field(default_factory=dict)

    trace: TraceBuffer = field(default_factory=TraceBuffer)

    error_details: str = ""

    messages_to_include: List[str] = field(default_factory=list)

    known_tools: List[str] = field(default_factory=list)
    enabled_tools: List[str] = field(default_factory=list)

    # "Pending action" slot: whichever tool the reasoner most recently
    # decided to call. Populated by react_reasoner_node, consumed by
    # tool_executor_node. Also doubles as the "tool awaiting confirmation"
    # reference while waiting_for is set.
    selected_tool: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    # The reasoning text that justified `selected_tool`, staged here by
    # react_reasoner_node until tool_executor_node turns it into a
    # ReActStep on the scratchpad.
    pending_thought: str = ""

    # Thought/Action/Observation history for the turn currently in progress.
    # Reset to [] at the start of every new user turn.
    scratchpad: List[ReActStep] = field(default_factory=list)
    max_react_steps: int = DEFAULT_MAX_REACT_STEPS

    tool_result: Optional[Dict[str, Any]] = None
    # Long-term memory of every tool result produced this session (kept
    # across turns so the reasoner can see what already ran and avoid
    # redundant calls). Trimmed by tool_executor._trim_tool_results.
    tool_results: Dict[str, Any] = field(default_factory=dict)
    tool_confirmation_needed: bool = False
    # Set to True right after the user confirms a pending creation tool, so that
    # tool_executor knows to actually run it instead of pausing again.
    tool_confirmed: bool = False

    def current_turn_result_keys(self) -> List[str]:
        """Ordered tool_results keys produced by the scratchpad of the turn
        currently in progress (i.e. this turn's observations only)."""
        return [
            step.observation_key for step in self.scratchpad if step.observation_key
        ]

    def _add_trace(
        self, step_type: str, node: str, data: Optional[Dict[str, Any]] = None
    ):
        self.trace.add_step(TraceStep(step_type=step_type, node=node, data=data))


@dataclass
class AgentState:
    # Interface layer
    conversation: ConversationBuffer = field(default_factory=ConversationBuffer)
    assistant_action_data: Optional[dict[str, Any]] = None

    # Orchestration
    token_used: int = 0
    session_id: str = ""
    user_lang: str = "English"
    integrated_mode: bool = False
    tenant: str = ""

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

    def add_trace(
        self,
        step_type: str,
        node: str | None = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.cognitive._add_trace(step_type=step_type, node=node, data=data)

    def add_user_message(self, content: str):
        self.conversation.add_message(ConversationMessage(role="user", content=content))

    def add_assistant_message(self, content: str):
        pipeline = self.cognitive.generation_pipeline

        def _provider_label(model_name: str) -> str:
            if model_name.startswith("claude"):
                return "anthropic"
            return f"{model_name}"

        labels = {_provider_label(m) for m in pipeline}

        if len(labels) == 0:
            generated_by = "unknown"
        elif len(labels) == 1:
            generated_by = labels.pop()
        else:
            generated_by = "mixed"

        self.conversation.add_message(
            ConversationMessage(
                role="assistant", content=content, generated_by=generated_by
            )
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
            return {
                f.name: self._serialize(getattr(obj, f.name))
                for f in dataclasses.fields(obj)
            }
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
