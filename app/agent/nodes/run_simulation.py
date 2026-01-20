from ..state import AgentState
from app.tools.simulation_tool import run_external_simulation

REQUIRED_FIELDS = ["model", "duration", "parameters"]

def extract_inputs(state: AgentState) -> AgentState:
    #TODO implement
    return state

def ask_missing(state: AgentState) -> AgentState:
    #TODO implement
    return state

def confirm(state: AgentState) -> AgentState:
    #TODO implement
    return state

def run_simulation(state: AgentState) -> AgentState:
    #TODO implement
    state.response = f"Simulation started"
    return state
