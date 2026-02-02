from ..state import AgentState
from app.tools.scenario_tool import run_external_scenario

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

def run_scenario(state: AgentState) -> AgentState:
    #TODO implement
    state.response = f"Scenario started"
    return state
