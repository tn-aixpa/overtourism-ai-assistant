from ..state import AgentState
from app.tools.simulation_tool import run_external_simulation

REQUIRED_FIELDS = ["model", "duration", "parameters"]

def extract_inputs(state: AgentState) -> AgentState:
    # VERY simple mock extraction
    text = state.user_message.lower()
    if "model" in text:
        state.pending_inputs["model"] = "default-model"
    if "duration" in text:
        state.pending_inputs["duration"] = 100
    if "parameter" in text:
        state.pending_inputs["parameters"] = {"alpha": 0.1}

    state.missing_inputs = [
        f for f in REQUIRED_FIELDS if f not in state.pending_inputs
    ]
    return state

def ask_missing(state: AgentState) -> AgentState:
    state.response = f"Missing inputs: {', '.join(state.missing_inputs)}"
    return state

def confirm(state: AgentState) -> AgentState:
    summary = "\n".join(
        f"{k}: {v}" for k, v in state.pending_inputs.items()
    )
    state.awaiting_confirmation = True
    state.response = f"Simulation summary:\n{summary}\n\nConfirm?"
    return state

def run_simulation(state: AgentState) -> AgentState:
    state.running_simulation = True
    sim_id = run_external_simulation(state.pending_inputs)
    state.sim1_id = sim_id
    state.running_simulation = False
    state.awaiting_confirmation = False
    state.pending_inputs = {}
    state.response = f"Simulation started with ID {sim_id}"
    return state
