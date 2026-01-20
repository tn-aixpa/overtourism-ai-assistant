
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict
from datetime import datetime

class SimulationInputs(TypedDict, total=False):
    model: str
    duration: int
    parameters: Dict[str, Any]

@dataclass
class AgentState:
    session_id: str = ""
    user_message: str = ""
    next_action: Optional[str] = None
    response: str = ""

    problem_id: str = ""
    scenario_ids: List[str] = field(default_factory=list)

    data: Dict[str, Any] = field(default_factory=dict)
    data_loaded_at: Optional[datetime] = None

    current_input: Dict[str, Any] = field(default_factory=dict)
    awaiting_confirmation: bool = False
    running_simulation: bool = False
    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)
