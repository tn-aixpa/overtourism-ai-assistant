
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict
from datetime import datetime

@dataclass
class AgentState:
    session_id: str = ""
    problem_id: str = ""
    scenario_ids: List[str] = field(default_factory=list)
    
    user_message: str = ""
    next_action: Optional[str] = None
    response: str = ""


    data: Dict[str, Any] = field(default_factory=dict)
    data_loaded_at: Optional[datetime] = None

    current_input: Dict[str, Any] = field(default_factory=dict)
    awaiting_confirmation: bool = False
    running_scenario: bool = False
    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)
