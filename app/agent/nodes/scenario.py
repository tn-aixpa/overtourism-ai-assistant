import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm_structured_extractions import extract_scenario_data
from app.utils.llm import parse_llm_json
from app.utils.common import parse_confirmation
from app.utils.messages import get_message, MessageCode
from app.utils.error_codes import get_error_message, ErrorCode
from app.tools.backend_tools import create_scenario_instance
from app.utils.backend_integration_classes import ScenarioInfoSchema, ScenarioInfo, build_schema_data

logger = logging.getLogger(__name__)

def assert_active_proposal(state: AgentState) -> Command:
    logger.info("Checking if there is an active proposal")
    state.add_trace("node_execution", node="assert_active_proposal")

    if state.cognitive.active_context_type == "proposal":
        state.resume_nome = {}
        return Command(update=state, goto="extract_scenario")

    # TODO: when multi-action is implemented remove this resume, keep only output message
    logger.info("No active prposal, asking user to activate it")
    state.resume_nome = {
        "node": "scenario_extraction",
        "subgraph": Command.PARENT
    }

    state.cognitive.messages_to_include = [get_error_message(ErrorCode.INVALID_CONTEXT, "English")]
    state.cognitive.additional_output_information = [
        f"Active contex: {state.get_active_context_string()}",
        state.cognitive.allowed_operations
    ]
    if state.cognitive.active_context_type == "problem":
        if state.cognitive.available_entries:
            available_proposals = state.cognitive.available_entries["connections_dict"]["problem_to_proposals"][state.cognitive.active_context[0]]
            state.cognitive.additional_output_information.append(
                "Suggested proposals, considering the active problem: " + ", ".join(available_proposals) 
            )

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

def extract_scenario(state: AgentState) -> AgentState:
    logger.info("Extracting scenario from reasoning context")
    answer = extract_scenario_data(state.get_reasoning_context(),
                                state.cognitive.editable_indexes)
    logger.info(f"Chatbot answer: {answer}")   

    assert "Error connecting to chatbot" not in answer
    
    scenarios = parse_llm_json(answer)       
    extracted_all_scenario = True
    schema = ScenarioInfoSchema.default()

    validated_scenarios: list[ScenarioInfo] = []
    validation_errors = []
    for scenario in scenarios:
        # validate indexes
        if "indexes_to_change" in scenario:
            validated_indexes = {}
            for key, value in scenario["indexes_to_change"].items():
                try:
                    min_val = state.cognitive.editable_indexes[key]["min"]
                    max_val = state.cognitive.editable_indexes[key]["max"]
                    step = state.cognitive.editable_indexes[key]["step"]
                    if value["type"] == "range":
                        current_val_min = value["value"][0]
                        current_val_max = value["value"][1]
                        if not (min_val <= current_val_min and current_val_max <= max_val and (current_val_max - min_val) % step == 0):
                            validation_errors.append(
                                f"The range [{current_val_min}-{current_val_max}] is not valid for index {key}. "
                                f"Please define an interval within [{min_val}-{max_val}] with step {step} "
                            )
                        else:
                            validated_indexes[key] = [current_val_min, current_val_max]
                    else:
                        base_val_min = state.cognitive.editable_indexes[key]["loc"]
                        base_val_max = base_val_min + state.cognitive.editable_indexes[key]["scale"]
                        if value["type"] == "increase":
                            current_val_max = base_val_max + value["value"]
                        else:
                            current_val_max = base_val_max - value["value"]
                        if not (current_val_max <= max_val and (current_val_max - min_val) % step == 0):
                            validation_errors.append(
                                f"The range [{base_val_min}-{current_val_max}] is not valid for index {key}. "
                                f"Please define an interval within [{min_val}-{max_val}] with step {step} "
                            )
                        else:
                            validated_indexes[key] = [base_val_min, current_val_max]
                except Exception as e:
                    validation_errors.append(f"Error parsing index {key}: {str(value)} is not valid - {e}.")

            try:
                scenario_data = {
                    "title": scenario.get("title"),
                    "description": scenario.get("description"),
                    "indexes_to_change": validated_indexes,
                }

                validated_scenarios.append(
                    build_schema_data(schema, scenario_data, ScenarioInfo)
                )
            except:
                extracted_all_scenario = False

    if not extracted_all_scenario:
        state.cognitive.extracted_all_scenario = False
        required_fields = [f for f, v in vars(state.cognitive.scenario_info_to_extract).items() if v.required]
        state.cognitive.validation_errors = (
            f"Not all scenarios include the required elements ({', '.join(required_fields)}).\nExtracted info"
        )
        state.cognitive.scenarios_to_generate = []
        state.cognitive.additional_output_information = [f"Extracted so far: {validated_scenarios}"]
        return state

    if not validation_errors:
        state.cognitive.extracted_all_scenario = True
        state.cognitive.validation_errors = ""
        state.cognitive.scenarios_to_generate = validated_scenarios
    else:
        state.cognitive.extracted_all_scenario = False
        state.cognitive.validation_errors = (
            "The following errors were detected for the scenarios you defined:\n- " + "\n- ".join(validation_errors)
        )
        state.cognitive.additional_output_information = [f"Extracted so far: {validated_scenarios}"]
        state.cognitive.scenarios_to_generate = []

    logger.info(
        f"Extracted scenarios: {state.cognitive.scenarios_to_generate}, "
        f"extracted_all_scenario: {state.cognitive.extracted_all_scenario}, "
        f"validation_errors: {state.cognitive.validation_errors}"
    )

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

    if state.cognitive.next_action == "WAIT_CONFIRMATION_SCENARIO":
        state.active_workflow = AgentState.Workflow.SCENARIO_EXTRACTION
        state.waiting_for = AgentState.WaitingFor.SCENARIO_CONFIRMATION
        state.user_input = None
        return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

    if state.cognitive.next_action == "CONFIRM_SCENARIO":
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto="run_scenario", graph="scenario_extraction")
    
    if state.cognitive.next_action == "CANCEL_SCENARIO":
        state.waiting_for = None
        state.user_input = None
        state.active_workflow = None
        state.cognitive.messages_to_include = [get_message(MessageCode.GENRAL_EXIT_MESSAGE, "English")]
        state.cognitive.additional_output_information = []
        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)
    
    # assume EDIT_SCENARIO
    state.waiting_for = None
    state.user_input = None
    return Command(update=state, goto="extract_scenario")


def run_scenario_node(state: AgentState) -> AgentState:
    if state.cognitive.scenarios_to_generate:
        state.add_trace("node_execution", node="run_scenario_node", data={"to_generate": len(state.cognitive.scenarios_to_generate)})
        current_scenario = state.cognitive.scenarios_to_generate.pop()
        logger.info(f"Running scenario: {current_scenario}")
        
        proposal_id = state.cognitive.active_context[0]

        problem_id = ""
        for problem, proposals in state.cognitive.available_entries["connections_dict"]["problem_to_proposals"].items():
            if proposal_id in proposals:
                problem_id = problem
                break
       
        result = create_scenario_instance.invoke({
            "problem_id": problem_id,
            "session_id": state.session_id,
            "scenario_name": current_scenario.title,
            "scenario_description": current_scenario.description,
            "values": current_scenario.indexes_to_change,
            "proposal_id": proposal_id,
        })

        logger.info(result)

        return Command(update=state, goto="run_scenario")
    else:
        state.resume_nome = {}
        state.active_workflow = None
        state.cognitive.messages_to_include = [get_message(MessageCode.SUCCESS_SCENARIO, "English")]
        state.cognitive.additional_output_information = []

        #TODO: decide if we want to activate this scenario or ask the user if he wants to activate it

        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)
    

################################################################33
# from app.utils.llm_reasoning import assess_scenario_strategy


# def decide_scenario_strategy(state: AgentState) -> AgentState:
#     logger.info("Deciding scenario generation strategy based on reasoning context.")
#     answer = assess_scenario_strategy(state.get_reasoning_context()).strip()

#     VALID_ACTIONS = {
#         "GENERATE_SCENARIOS",
#         "GENERATE_AGENTIC_SCENARIOS",
#         "ASK_USER_PREFERENCE",
#         "NO_SCENARIOS",
#     }

#     if answer not in VALID_ACTIONS:
#         state.cognitive.next_action = "ASK_USER_PREFERENCE"
#     else:
#         state.cognitive.next_action = answer

#     logger.info(f"Decided scenario generation strategy: {state.cognitive.next_action}")
#     return state



# def decide_strategy_node(state: AgentState):
#     logger.info("Entering scenario strategy decision node")
#     state = decide_scenario_strategy(state)
#     state.add_trace("node_execution", node="decide_strategy_node", data={"intent": state.cognitive.next_action})

#     logger.info(f"Decided next action based on scenario strategy: {state.cognitive.next_action}")
#     if state.cognitive.next_action == "GENERATE_SCENARIOS":
#         state.waiting_for = None
#         return Command(update=state, goto="scenario_extraction", graph=Command.PARENT)
#     if state.cognitive.next_action == "GENERATE_AGENTIC_SCENARIOS":
#         state.waiting_for = None
#         return Command(update=state, goto="generate_scenario_candidates", graph=Command.PARENT)
#     if state.cognitive.next_action == "ASK_USER_PREFERENCE":
#         state.active_workflow = AgentState.Workflow.PROBLEM
#         state.waiting_for = AgentState.WaitingFor.SCENARIO_PREFERENCE
#         state.user_input = None
#         return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)
#     if state.cognitive.next_action == "NO_SCENARIOS":
#         state.waiting_for = None
#         state.cognitive.messages_to_include = [get_message(MessageCode.GENRAL_EXIT_MESSAGE, "English")]
#         state.cognitive.additional_output_information = []

#         return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

#     raise ValueError(f"Invalid scenario strategy action: {state.cognitive.next_action}")