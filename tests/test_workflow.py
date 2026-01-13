from dataclasses import replace

from app.agent.graph import app
from app.agent.state import AgentState


def test_full_workflow_invalid(empty_state):
    state = replace(empty_state)
    state.user_message = "Tell me about the weather in Paris"

    result = app.invoke(state)
    assert result["response"] == "I'm not able to handle this request with the current system capabilities."
    
def test_full_workflow_interact():
    MOCK_SIMULATION_DATA = {
        "visitors": {
            "monthly_average": 120000,
            "peak_month": "August",
            "capacity": 90000
        },
        "infrastructure": {
            "parking_spaces": 3000,
            "public_transport_load": 0.92
        },
        "environment": {
            "co2_index": 1.35,
            "protected_area_pressure": "high"
        }
    }
        
    state = AgentState(
        user_message="Analyze the simulation and propose policies with environmental impacts and infrastructure changes.",
        sim1_id="sim_001",
        sim2_id=None,
        simulation_data=MOCK_SIMULATION_DATA,
        simulation_data_loaded_at="2024-01-01T10:00:00Z",
        pending_inputs={},
        missing_inputs=[],
        awaiting_confirmation=False,
        running_simulation=False,
        expert_answers={},
        next_action=None,
        response="",
    )

    result = app.invoke(state)
    assert result["next_action"] == "INTERACT_SIMULATION"
    assert len(result["selected_roles"]) > 1
    assert result["response"] != "" and "not able to handle this request" not in result["response"]
    

def test_full_workflow_compare(empty_state):
    pass

def test_full_workflow_run_simulation(empty_state):
    pass