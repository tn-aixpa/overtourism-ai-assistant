
from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict
from datetime import datetime

class SimulationInputs(TypedDict, total=False):
    model: str
    duration: int
    parameters: Dict[str, Any]

class AgentState(TypedDict):
    user_message: str

    sim1_id: Optional[str]
    sim2_id: Optional[str]

    simulation_data: Optional[Dict[str, Any]]
    simulation_data_loaded_at: Optional[datetime]

    interact_blocked_until: Optional[datetime]


    pending_inputs: SimulationInputs
    missing_inputs: List[str]
    awaiting_confirmation: bool
    running_simulation: bool

    next_action: Optional[str]
    response: str
