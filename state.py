
from typing import Optional, Dict, Any, List
from typing_extensions import TypedDict

class SimulationInputs(TypedDict, total=False):
    model: str
    duration: int
    parameters: Dict[str, Any]

class AgentState(TypedDict):
    user_message: str

    simulation_id: Optional[str]
    sim1: Optional[str]
    sim2: Optional[str]

    pending_inputs: SimulationInputs
    missing_inputs: List[str]
    awaiting_confirmation: bool
    running_simulation: bool

    next_action: Optional[str]
    response: str
