import json
from ..state import AgentState
from ...utils.llm import extract_problem_data
from ...utils.llm import assess_scenario_strategy

def extract_problem(state: AgentState) -> AgentState:
    #TODO: might need to revise to add the possiblity to change/integrate/remove a field
    answer = extract_problem_data(state.messages[-1]["content"] if state.messages else "",
                                  state.problem_info,
                                  state.extracted_problem_info)
    
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

def decide_scenario_strategy(state: AgentState) -> AgentState:
    answer = assess_scenario_strategy(state.messages)
    if "Error" in answer:  
        state.next_action = "ASK_USER_PREFERENCE"
    else:
        state.next_action = answer
    return state

def validate_scenarios():
    pass

def generate_scenario_candidates():
    pass