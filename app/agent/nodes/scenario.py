import logging
import json
from langgraph.graph import END
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm import extract_scenario_data
from app.utils.common import parse_confirmation
from app.utils.messages import get_message, MessageCode

logger = logging.getLogger(__name__)

def extract_scenario(state: AgentState) -> AgentState:
    logger.info("Extracting scenario from reasoning context")
    answer = extract_scenario_data(state.get_reasoning_context(),
                                state.cognitive.editable_indexes)   

    assert "Error connecting to chatbot" not in answer
    
    #TODO: check if it reasonable

    scenarios = json.loads(answer)       
    extracted_all_scenario = True
    required_fileds = [f for f, v in state.cognitive.scenario_info_to_extract.items() if v["required"]]
    validated_scenarios = {}
    for scenario in scenarios:
        if not all(elem in scenario for elem in required_fileds):    
            extracted_all_scenario = False
            break

        # validate indexes
        validation_errors = []
        if "indexes_to_change" in scenario:
            validated_scenarios[scenario['title']] = []
            for key, value in scenario["indexes_to_change"].items():
                try:
                    min_val = state.cognitive.editable_indexes[key]["min"]
                    max_val = state.cognitive.editable_indexes[key]["max"]
                    step = state.cognitive.editable_indexes[key]["step"]
                    if value["type"] == "range":
                        current_val_min = value["value"][0]
                        current_val_max = value["value"][1]
                        if not (current_val_min <= current_val_min and current_val_max <= max_val and (current_val_max - min_val) % step == 0):
                            validation_errors.append(f"The range [{current_val_min}-{current_val_max}] is not valid for index {key}. Please define an interval within [{min_val}-{max_val}] with step {step} ")
                        else:
                            validated_scenarios[scenario['title']].append({key: [current_val_min, current_val_max]})
                    else:
                        base_val_min = state.cognitive.editable_indexes[key]["loc"]
                        base_val_max = base_val_min + state.cognitive.editable_indexes[key]["scale"]
                        if value["type"] == "increase":
                            increase_val = value["value"]
                            current_val_max = base_val_max + increase_val
                        else:
                            decrease_val = value["value"]
                            current_val_max = base_val_max - decrease_val
                        if not (current_val_max <= max_val and (current_val_max - min_val) % step == 0):
                            validation_errors.append(f"The range [{base_val_min}-{current_val_max}] is not valid for index {key}. Please define an interval within [{min_val}-{max_val}] with step {step} ")
                        else:
                            validated_scenarios[scenario['title']].append({key: [base_val_min, current_val_max]})
                except Exception as e:
                    validation_errors.append(f"Error parsing index {key}: {str(value)} is not valid.")       
    
    if not extracted_all_scenario:
        state.cognitive.extracted_all_scenario = False
        state.cognitive.validation_errors =  f""""Not all scenarios include the required elements ({', '.join(required_fileds)}).\nExtracted info"""
        state.cognitive.scenarios_to_generate = None
        return state
    if not len(validation_errors):
        state.cognitive.extracted_all_scenario = True
        state.cognitive.validation_errors = ""
        state.cognitive.scenarios_to_generate = validated_scenarios
    else:
        state.cognitive.extracted_all_scenario = False
        state.cognitive.validation_errors = "The following errors were dected for the scenarios you defined:\n" + "\n- ".join(validation_errors) 
        state.cognitive.scenarios_to_generate = None

    logger.info(f"Extracted scenarios: {state.cognitive.scenarios_to_generate}, extracted_all_scenario: {state.cognitive.extracted_all_scenario}, validation_errors: {state.cognitive.validation_errors}")

    return state

def extract_scenario_node(state: AgentState):
    logger.info("Entering extract_scenario_node")
    state = extract_scenario(state)
    state.add_trace("node_execution", node="extract_scenario_node", data={"extracted": state.cognitive.scenarios_to_generate,"extracted_all_scenario": state.cognitive.extracted_all_scenario,})
    state.active_workflow = AgentState.Workflow.SCENARIO_EXTRACTION
    state.user_input = None

    if state.cognitive.scenarios_to_generate:
        state.waiting_for = AgentState.WaitingFor.SCENARIO_CONFIRMATION
    else:
        state.waiting_for = AgentState.WaitingFor.SCENARIO_INPUT

    return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

def parse_confirmation_node(state: AgentState):
    logger.info("Entering parse_confirmation_node")
    message = state.get_last_user_message().content_en
    
    state.cognitive.next_action = parse_confirmation(message)+'_SCENARIO'
    logger.info(f"Parsed user confirmation: {state.cognitive.next_action}")

    state.add_trace("node_execution", node="parse_confirmation_node", data={"next_action": state.cognitive.next_action})

    if state.cognitive.next_action == "CONFIRM_SCENARIO":
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto="scenario_runner", graph=Command.PARENT) 
    
    routes = {
        "EDIT_SCENARIO": "extract_scenario",
        "CANCEL_SCENARIO": END,
    }
    if state.cognitive.next_action == "WAIT_CONFIRMATION_SCENARIO":
        state.active_workflow = AgentState.Workflow.SCENARIO_EXTRACTION
        state.waiting_for = AgentState.WaitingFor.SCENARIO_CONFIRMATION
        state.user_input = None
        return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

    state.waiting_for = None
    state.user_input = None
    return Command(update=state, goto=routes[state.cognitive.next_action])


def run_scenario_node(state: AgentState) -> AgentState:
    if state.cognitive.scenarios_to_generate:
        logger.info(f"Running scenario with parameters: {state.cognitive.scenarios_to_generate}")
        state.add_trace("node_execution", node="run_scenario_node", data={"to_generate": len(state.cognitive.scenarios_to_generate)})
        scenario_title, scenario_parameters = state.cognitive.scenarios_to_generate.popitem()
        #TODO: run tool
        return Command(update=state, goto="run_scenario")
    else:
        state.add_assistant_message(
            get_message(MessageCode.SUCCESS_SCENARIO, state.user_lang),
            get_message(MessageCode.SUCCESS_SCENARIO, "English")
        )
        logger.info("No scenarios to run.")
        return Command(update=state, goto="END")