
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
    user_message: str

    sim1_id: Optional[str] = None
    sim2_id: Optional[str] = None

    simulation_data: Dict[str, Any] = field(default_factory=dict)
    simulation_data_loaded_at: Optional[datetime] = None

    pending_inputs: Dict[str, Any] = field(default_factory=dict)
    missing_inputs: List[str] = field(default_factory=list)
    awaiting_confirmation: bool = False
    running_simulation: bool = False

    selected_roles: List[str] = field(default_factory=list)
    expert_answers: Dict[str, str] = field(default_factory=dict)

    next_action: Optional[str] = None
    response: str = ""

    def get_active_simulations(self) -> list[str]:
        return [s for s in (self.sim1_id, self.sim2_id) if s]
