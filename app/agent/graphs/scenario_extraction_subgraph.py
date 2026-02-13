import json
from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import extract_scenario_data
from .utils import human_gate, safe

# ---- Nodes

def extract_scenario(state: AgentState) -> AgentState:
    answer = extract_scenario_data(state.messages,
                                  state.scenario_info_to_extract,
                                  state.editable_idexes)
    

    if "Error connecting to Ollama" not in answer:
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

    else:
      #TODO: impement
      pass
    return state

# ---- Human gates

wait_scenario_input = human_gate(
    "WAIT_SCENARIO_INPUT",
    lambda s: {"instructions": s.error_message + f"\nPlease, provide all required details to create a scenario"},
)

wait_scenario_confirmation = human_gate(
    "WAIT_SCENARIO_CONFIRMATION",
    lambda s: {"instructions": "Do you want to proceed with the following scenarios?", "scenario_info_to_extract": s.scenarios_to_generate},
)

# ---- Command wrappers

def extract_scenario_node(state: AgentState):
    state = extract_scenario(state)
    #state = safe(extract_scenario)(state)
    Command(update=state, goto=END)
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


# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("extract_scenario", extract_scenario_node)
graph.add_node("WAIT_SCENARIO_INPUT", wait_scenario_input)
graph.add_node("WAIT_SCENARIO_CONFIRMATION", wait_scenario_confirmation)
graph.add_node("parse_scenario_confirmation", parse_confirmation_node)

graph.set_entry_point("extract_scenario")

graph.add_edge("WAIT_SCENARIO_CONFIRMATION", "parse_scenario_confirmation")
graph.add_edge("WAIT_SCENARIO_INPUT", "extract_scenario")

scenario_extraction_subgraph = graph.compile()
