
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict
from datetime import datetime

@dataclass
class AgentState:
    # Core state
    user_message: str = ""
    next_action: Optional[str] = None
    response: str = ""

    # Parameters related to questions
    session_id: str = ""
    problem_id: str = ""
    scenario_ids: List[str] = field(default_factory=list)
    
    data: Dict[str, Any] = field(default_factory=dict)
    data_loaded_at: Optional[datetime] = None

    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)

    # Problem creation
    problem_info: Dict[str, Any] = field(default_factory=dict)
    extracted_problem_info: Dict[str, Any] = field(default_factory=dict)
    extracted_all_problem: bool = False

    # Scenario creation
    required_scenario_info: Dict[str, Any] = field(default_factory=dict)
    extracted_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    validated_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    scenario_preferences: Dict[str, Any] = field(default_factory=dict)
    scenario_strategy: Optional[str] = None
    scenario_candidates: List[Dict[str, Any]] = field(default_factory=list)

    # Scenario execution
    prepared_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    scenario_results: Dict[str, Any] = field(default_factory=dict)
    current_input: Dict[str, Any] = field(default_factory=dict)
    awaiting_confirmation: bool = False
    running_scenario: bool = False
