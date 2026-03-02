
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.config import MAX_CONTEXT_WINDOW

@dataclass
class ConversationMessage:
    role: str  # "user" | "assistant"
    content_localized: str  # localized user-facing content(e.g. Italian)
    content_en: str
    timestamp: Optional[datetime] = None

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
class CognitiveState:
    # Canonical reasoning language: ENGLISH

    # Routing
    next_action: Optional[str] = None

    # Problem context
    problem_id: str = ""
    problem_info_to_extract: Dict[str, Any] = field(default_factory=dict)
    extracted_problem_info: Dict[str, Any] = field(default_factory=dict)
    extracted_all_problem: bool = False

    # Scenario context
    scenario_ids: List[str] = field(default_factory=list)
    scenario_info_to_extract: Dict[str, Any] = field(default_factory=dict)
    extracted_all_scenario: bool = False

    # Execution state
    scenarios_to_generate: List[Dict[str, Any]] = field(default_factory=list)
    validation_errors: str = ""

    # Expert reasoning
    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)

    # Data layer
    data: Dict[str, Any] = field(default_factory=dict)
    editable_indexes: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentState:
    # Interface layer (Localized language only)
    conversation: ConversationBuffer = field(default_factory=ConversationBuffer)

    # Orchestration Layer (English only)
    session_id: str = ""
    user_lang: str = "English"

    # Cognitive Layer (English only)
    cognitive: CognitiveState = field(default_factory=CognitiveState)

    # Error handling
    error_code: str = ""
    error_node: str = ""
    error_details: str = ""

    # ---- Methods ----

    def add_user_message(self, localized: str, translated_en: str):
        self.conversation.add_message(
            ConversationMessage(
                role="user",
                content_localized=localized,
                content_en=translated_en,
                timestamp=datetime.now()
            )
        )

    def add_assistant_message(self, localized: str, translated_en: str):
        self.conversation.add_message(
            ConversationMessage(
                role="assistant",
                content_localized=localized,
                content_en=translated_en,
                timestamp=datetime.now()
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

    def get_reasoning_context(self, n: Optional[int] = None):
        return self.conversation.get_context_window_en(n)

    def get_ui_context(self, n: Optional[int] = None):
        return self.conversation.get_context_window_localized(n)
