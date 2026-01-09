
from dataclasses import dataclass
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

    simulation_data: Optional[Dict[str, Any]] = None
    simulation_data_loaded_at: Optional[datetime] = None

    interact_blocked_until: Optional[datetime] = None

    pending_inputs: Dict[str, Any] = None
    missing_inputs: List[str] = None
    awaiting_confirmation: bool = False
    running_simulation: bool = False

    next_action: Optional[str] = None
    response: str = ""

    def get_active_simulations(self) -> list[str]:
        return [s for s in (self.sim1_id, self.sim2_id) if s]
