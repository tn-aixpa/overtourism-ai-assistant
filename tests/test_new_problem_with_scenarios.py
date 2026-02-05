import pytest
from dataclasses import replace

from app.agent.graph import app
from app.agent.state import AgentState
from tests.conftest import empty_state

def test_problem_creation_with_agentic_scenario(empty_state):
    state = replace(empty_state)
    state.user_message = "In Molveno there is a problem related to the fact that there are not enough parking spaces which leads to people parking off-spot and long queues. The administration would like to have 3 different strategies to tackle this problem."
    state.problem_info = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem", "required": True},
        "available subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False}
    }
    events = []
    with open("logs/test_new_problem_with_scenarios_events.log", "w") as f:
        for event in app.stream(state):
            f.write(f"Event: {event}\n")
            events.append(event)

    # for event in app.stream(state):
    #     events.append(event)

    #     # Inspect current node
    #     node = event["node"]
    #     current_state = event["state"]

    #     # ---- Simulate user replies ----
    #     if node == "ask_missing_problem":
    #         current_state.messages.append({
    #             "role": "user",
    #             "content": "The problem is about supplier concentration risk in Asia"
    #         })

    #     elif node == "ask_scenario_preference":
    #         current_state.messages.append({
    #             "role": "user",
    #             "content": "You decide the scenarios"
    #         })

    # # ---- Assertions ----

    # node_names = [e["node"] for e in events]

    # assert "extract_problem" in node_names
    # assert "confirm_problem" in node_names
    # assert "generate_scenario_candidates" in node_names
    # assert "prepare_scenarios" in node_names
    # assert "run_scenario" in node_names

    # final_state = events[-1]["state"]

    # assert final_state.scenarios
    # assert final_state.problem_data is not None



# def test_full_workflow_invalid(empty_state):
#     state = replace(empty_state)
#     state.user_message = "Tell me about the weather in Paris"

#     result = app.invoke(state)
#     assert result["response"] == "I'm not able to handle this request with the current system capabilities."
    
# def test_full_workflow_interact():
#     MOCK_data = {"sim_001" :{
#         "visitors": {
#             "monthly_average": 120000,
#             "peak_month": "August",
#             "capacity": 90000
#         },
#         "infrastructure": {
#             "parking_spaces": 3000,
#             "public_transport_load": 0.92
#         },
#         "environment": {
#             "co2_index": 1.35,
#             "protected_area_pressure": "high"
#         }
#     }}
        
#     state = AgentState(
#         user_message="Analyze the scenario and propose policies with environmental impacts and infrastructure changes.",
#         next_action=None,
#         response="",
#         problem_id="",
#         scenario_ids=["sim_001"],
#         data=MOCK_data,
#         data_loaded_at="2024-01-01T10:00:00Z",
#         current_input={},
#         awaiting_confirmation=False,
#         running_scenario=False,
#         expert_answers={},
#     )

#     result = app.invoke(state)
#     assert result["next_action"] == "INTERACT_SCENARIO"
#     assert len(result["selected_roles"]) > 1
#     assert result["response"] != "" and "not able to handle this request" not in result["response"]
    

# def test_full_workflow_compare():
#     MOCK_data = {
#         "sim_001": {    
#             "visitors": {
#                 "monthly_average": 120000,
#                 "peak_month": "August",
#                 "capacity": 90000
#             },
#             "infrastructure": {
#                 "parking_spaces": 3000,
#                 "public_transport_load": 0.92
#             },
#             "environment": {
#                 "co2_index": 1.35,
#                 "protected_area_pressure": "high"
#             }
#         },
#         "sim_002": {    
#             "visitors": {
#                 "monthly_average": 80000,
#                 "peak_month": "August",
#                 "capacity": 90000
#             },
#             "infrastructure": {
#                 "parking_spaces": 2500,
#                 "public_transport_load": 0.92
#             },
#             "environment": {
#                 "co2_index": 0.35,
#                 "protected_area_pressure": "high"
#             }
#         }
#     }
        
#     state = AgentState(
#         user_message="What are the impacts of reducing the number of parking spaces? How will this impact mobility and environment?",
#         next_action=None,
#         response="",
#         problem_id="",
#         scenario_ids=["sim_001", "sim_002"],
#         data=MOCK_data,
#         data_loaded_at="2024-01-01T10:00:00Z",
#         current_input={},
#         awaiting_confirmation=False,
#         running_scenario=False,
#         expert_answers={},
#     )

#     result = app.invoke(state)
#     assert result["next_action"] == "COMPARE_SCENARIOS"
#     assert len(result["selected_roles"]) > 1
#     assert result["response"] != "" and "not able to handle this request" not in result["response"]

# def test_full_workflow_run_scenario(empty_state):
#     pass