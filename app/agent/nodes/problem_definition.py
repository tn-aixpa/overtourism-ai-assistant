import json
from ..state import AgentState
from ...utils.llm import extract_problem_data

def extract_problem(state: AgentState) -> AgentState:

    answer = extract_problem_data(state.user_message, state.problem_info, state.extracted_problem_info)
    
    #"problem_title": "Insufficient Parking Spaces in Molveno",\n  "objectives": "To provide sufficient parking spaces, reduce off-spot parking, and eliminate long queues",\n  "problem_description": "The lack of parking spaces in Molveno results in people parking off-spot and forming long queues. This issue needs to be addressed to ensure smooth traffic flow and prevent congestion.",\n  "additional_data": "The current situation is causing inconvenience to visitors and locals alike.",\n  "available_subsystems": "Parking management, Traffic management, Urban planning"\n}',

    if "Error" not in answer:

        try:
            # The LLM output should be JSON, so we load it
            parsed_data = json.loads(answer)
        except json.JSONDecodeError:
            return {}

        for key, value in parsed_data.items():
            state.extracted_problem_info[key] = value
        
        state.extracted_all_problem = True
        for key, info in state.problem_info.items():
            if info["required"] and key not in state.extracted_problem_info:
                # If any required info is missing, we consider the extraction incomplete
                state.extracted_all_problem = False
                break

    else:
      #TODO: impement
      pass
    return state
    
def ask_missing_problem():
    pass

def confirm_problem():
    pass

def decide_scenario_strategy():
    pass
def ask_scenario_preference():
    pass
def collect_user_scenarios():
    pass
def validate_scenarios():
    pass
def confirm_user_scenarios():
    pass
def generate_scenario_candidates():
    pass