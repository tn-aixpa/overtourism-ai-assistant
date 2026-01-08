from state import AgentState
from datetime import datetime, timedelta

def interact_simulation(state: AgentState) -> AgentState:
    now = datetime.now()

    # block guard
    if state["interact_blocked_until"] and now < state["interact_blocked_until"]:
        state["response"] = blocked_message(state["interact_blocked_until"])
        return state

    # load data if needed
    if state["simulation_data"] is None:
        try:
            data = load_simulation_data(state["sim1_id"])
            state["simulation_data"] = data
            state["simulation_data_loaded_at"] = now
        except Exception:
            state["interact_blocked_until"] = now + timedelta(hours=2)
            state["response"] = "Simulation data is not available right now. Please try again later."
            return state

    # answer user question
    if not question_answerable(state["user_message"], state["simulation_data"]):
        state["response"] = (
            "I can’t answer this question based on the available data "
            "or my expertise as a data analyst."
        )
        return state

    state["response"] = answer_question(
        question=state["user_message"],
        data=state["simulation_data"],
        role="data analyst",
    )

    return state

def blocked_message(until: datetime) -> str:
    """
    Return a user-facing message explaining that interaction is blocked.
    """
    readable_time = until.strftime("%Y-%m-%d %H:%M")
    return (
        "Simulation data for this run is currently unavailable.\n"
        f"Please try again after {readable_time}."
    )

def load_simulation_data(sim1_id: str) -> dict:
    """
    Retrieve simulation data associated with a simulation ID.

    Raises:
        RuntimeError if data cannot be retrieved.
    """
    if sim1_id is None:
        raise RuntimeError("No simulation_id provided")

    # Placeholder: replace with real download logic
    data = {
        "metrics": {
            "travel_time": [10, 12, 15],
            "co2_emissions": [100, 120, 130],
        },
        "metadata": {
            "sim1_id": sim1_id,
        },
    }

    if not data:
        raise RuntimeError("Simulation data not found")

    return data

def question_answerable(question: str, data: dict) -> bool:
    """
    Check whether the question can be answered using available data
    and the expertise of the agent.
    """
    if not question or not data:
        return False

    # TODO: define logic: e.g with keywords

    return True

def answer_question(question: str, data: dict, role: str):
    return f"Interacting with simulation. (Mock reasoning over results)"