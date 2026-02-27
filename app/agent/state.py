
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime

@dataclass
class ConversationMessage:
    role: str  # "user" | "assistant"
    content: str  # Localized (Italian)
    timestamp: Optional[datetime] = None

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

    #TODO: Add memory if more than one message is required
    # recent_window: List[Dict[str, str]] = field(default_factory=list) - last 1-3 messages
    # conversation_summary_en: Optional[str] = None


@dataclass
class AgentState:
    # Interface layer (Current language only)
    conversation: List[ConversationMessage] = field(default_factory=list)

    # Orchestration Layer (English only)
    session_id: str = ""
    last_user_en: Optional[str] = None  # translated latest user message
    user_lang: str = "English"

    # Cognitive Layer (English only)
    cognitive: CognitiveState = field(default_factory=CognitiveState)

    # Error handling
    error_code: str = ""
    error_details: str = ""

