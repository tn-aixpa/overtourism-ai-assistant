import json
from langgraph.graph import END
from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import extract_scenario_data

def extract_scenario(state: AgentState) -> AgentState:
    answer = extract_scenario_data(state.messages,
                                state.scenario_info_to_extract,
                                state.editable_idexes)   

    assert "Error connecting to Ollama" not in answer
    
    #TODO: check if it reasonable

    scenarios = json.loads(answer)       
    extracted_all_scenario = True
    required_fileds = [f for f, v in state.scenario_info_to_extract.items() if v["required"]]
    validated_scenarios = {}
    for scenario in scenarios:
        if not all(elem in scenario for elem in required_fileds):    
            extracted_all_scenario = False
            break

        # validate indexes
        messages = []
        if "indexes_to_change" in scenario:
            validated_scenarios[scenario['title']] = []
            for key, value in scenario["indexes_to_change"].items():
                try:
                    min_val = state.editable_idexes[key]["min"]
                    max_val = state.editable_idexes[key]["max"]
                    step = state.editable_idexes[key]["step"]
                    if value["type"] == "range":
                        current_val_min = value["value"][0]
                        current_val_max = value["value"][1]
                        if not (current_val_min <= current_val_min and current_val_max <= max_val and (current_val_max - min_val) % step == 0):
                            messages.append(f"The range [{current_val_min}-{current_val_max}] is not valid for index {key}. Please define an interval within [{min_val}-{max_val}] with step {step} ")
                        else:
                            validated_scenarios[scenario['title']].append({key: [current_val_min, current_val_max]})
                    else:
                        base_val_min = state.editable_idexes[key]["loc"]
                        base_val_max = base_val_min + state.editable_idexes[key]["scale"]
                        if value["type"] == "increase":
                            increase_val = value["value"]
                            current_val_max = base_val_max + increase_val
                        else:
                            decrease_val = value["value"]
                            current_val_max = base_val_max - decrease_val
                        if not (current_val_max <= max_val and (current_val_max - min_val) % step == 0):
                            messages.append(f"The range [{base_val_min}-{current_val_max}] is not valid for index {key}. Please define an interval within [{min_val}-{max_val}] with step {step} ")
                        else:
                            validated_scenarios[scenario['title']].append({key: [base_val_min, current_val_max]})
                except Exception as e:
                    messages.append(f"Error parsing index {key}: {str(value)} is not valid.")       
    
    if not extracted_all_scenario:
        state.extracted_all_scenario = False
        state.error_message =  f""""Not all scenarios include the required elements ({', '.join(required_fileds)}).\nExtracted info"""
        state.scenarios_to_generate = None
        return state
    if not len(messages):
        state.extracted_all_scenario = True
        state.error_message = None
        state.scenarios_to_generate = validated_scenarios
    else:
        state.extracted_all_scenario = False
        state.error_message = "The following errors were dected for the scenarios you defined:\n" + "\n- ".join(messages) 
        state.scenarios_to_generate = None

    return state

def extract_scenario_node(state: AgentState):
    state = extract_scenario(state)
    if state.scenarios_to_generate:
        return Command(update=state, goto="WAIT_SCENARIO_CONFIRMATION")
    return Command(update=state, goto="WAIT_SCENARIO_INPUT")

def parse_confirmation_node(state: AgentState):
    message = state.messages[-1]["content"].lower() if state.messages else ""
    if any(word in message for word in ["yes", "confirm", "ok"]):
        state.next_action = "CONFIRM_SCENARIO"
    elif any(word in message for word in ["edit", "change", "modify"]):
        state.next_action = "EDIT_SCENARIO"
    elif any(word in message for word in ["cancel", "interrut", "quit"]) or message == "no":
        state.next_action = "CANCEL_SCENARIO"
    else:
        state.next_action = "WAIT_SCENARIO_CONFIRMATION"
    #TODO: add also llm fallback

    if state.next_action == "CONFIRM_SCENARIO":
        return Command(update=state, goto="scenario_runner", graph=Command.PARENT) 
    
    routes = {
        "EDIT_SCENARIO": "extract_scenario",
        "CANCEL_SCENARIO": END,
        "WAIT_SCENARIO_CONFIRMATION": "WAIT_SCENARIO_CONFIRMATION",
    }
    return Command(update=state, goto=routes[state.next_action])


def run_scenario_node(state: AgentState) -> AgentState:
    if state.scenarios_to_generate:
        scenario_title, scanario_parameters = state.scenarios_to_generate.popitem()
        #TODO: run tool
        return Command(update=state, goto="run_scenario")
    else:
        state.messages.append(
            {
                "role": "assistant",
                "content": "I created the requested scenarios." 
            }
        )
        return Command(update=state, goto="END")