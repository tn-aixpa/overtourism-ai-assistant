
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict
from datetime import datetime

@dataclass
class AgentState:
    # Core state
    messages: List[Dict[str, Any]] = field(default_factory=list) # contains dict in format {"role": "user"/"assistant", "content": "...message content..."}
    next_action: Optional[str] = None

    # Parameters related to questions
    session_id: str = ""
    problem_id: str = ""
    scenario_ids: List[str] = field(default_factory=list)
    
    data: Dict[str, Any] = field(default_factory=dict)
    data_loaded_at: Optional[datetime] = None

    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)

    # Problem creation
    problem_info_to_extract: Dict[str, Any] = field(default_factory=dict)
    extracted_problem_info: Dict[str, Any] = field(default_factory=dict)
    extracted_all_problem: bool = False

    # Scenario creation
    scenario_info_to_extract: Dict[str, Any] = field(default_factory=dict)
    extracted_scenario_info: List[Dict[str, Any]] = field(default_factory=list)
    validated_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    scenarios_to_generate : List[Dict[str, Any]] = field(default_factory=list)

    # Scenario execution
    running_scenario: bool = False
