import logging
from langgraph.types import Command

from app.agent.events import publish
from app.agent.state import AgentState
from app.utils.llm_structured_extractions import extract_scenario_data
from app.utils.llm import parse_llm_json
from app.agent.nodes.general import parse_confirmation
from app.utils.messages import get_message, MessageCode
from app.tools.backend_tools import create_scenario_instance, get_sliders
from app.utils.backend_integration_classes import ScenarioInfoSchema, ScenarioInfo, build_schema_data
from app.config import SYSTEM_DESCRIPTION
from app.utils.common import get_available_entries_if_missing

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
        "node": "new_scenario",
        "subgraph": Command.PARENT
    }

    state.cognitive.messages_to_include = [get_message(MessageCode.INVALID_CONTEXT)]
    state = get_available_entries_if_missing(state)
    state.cognitive.additional_output_information = [
        f"Active contex: {state.get_active_context_string()}",
        SYSTEM_DESCRIPTION,
        state.cognitive.available_entries
    ]
    if state.cognitive.active_context_type == "problem":
        if state.cognitive.available_entries:
            available_proposals = state.cognitive.available_entries["connections_dict"]["problem_to_proposals"][state.cognitive.active_context[0]]
            state.cognitive.additional_output_information.append(
                "Suggested proposals, considering the active problem: " + ", ".join(available_proposals) 
            )

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)


# def extract_scenario_old(state: AgentState) -> Command:
#     logger.info("Entering extract_scenario")
#     publish(state.session_id, "Extracting information from your input...")

#     answer = extract_scenario_data(state)
#     logger.info(f"Chatbot answer: {answer}")   
    
#     scenarios = parse_llm_json(answer)       
#     schema = ScenarioInfoSchema.default()

#     validated_scenarios: list[ScenarioInfo] = []
#     scenario_validation_errors = []
#     for scenario in scenarios:
#         # validate indexes
#         if "indexes_to_change" in scenario:
#             validated_indexes = {}
#             for key, value in scenario["indexes_to_change"].items():
#                 try:
#                     min_val = state.cognitive.editable_indexes[key]["min"]
#                     max_val = state.cognitive.editable_indexes[key]["max"]
#                     step = state.cognitive.editable_indexes[key]["step"]
#                     if value["type"] == "range":
#                         current_val_min = value["value"][0]
#                         current_val_max = value["value"][1]
#                         if not (min_val <= current_val_min and current_val_max <= max_val and (current_val_max - min_val) % step == 0):
#                             scenario_validation_errors.append(
#                                 f"The range [{current_val_min}-{current_val_max}] is not valid for index {key}. "
#                                 f"Please define an interval within [{min_val}-{max_val}] with step {step} "
#                             )
#                         else:
#                             validated_indexes[key] = [current_val_min, current_val_max]
#                     else:
#                         base_val_min = state.cognitive.editable_indexes[key]["loc"]
#                         base_val_max = base_val_min + state.cognitive.editable_indexes[key]["scale"]
#                         if value["type"] == "increase":
#                             current_val_max = base_val_max + value["value"]
#                         else:
#                             current_val_max = base_val_max - value["value"]
#                         if not (current_val_max <= max_val and (current_val_max - min_val) % step == 0):
#                             scenario_validation_errors.append(
#                                 f"The range [{base_val_min}-{current_val_max}] is not valid for index {key}. "
#                                 f"Please define an interval within [{min_val}-{max_val}] with step {step} "
#                             )
#                         else:
#                             validated_indexes[key] = [base_val_min, current_val_max]
#                 except Exception as e:
#                     scenario_validation_errors.append(f"Error parsing index {key}: {str(value)} is not valid - {e}.")

#             try:
#                 scenario_data = {
#                     "title": scenario.get("title"),
#                     "description": scenario.get("description"),
#                     "indexes_to_change": validated_indexes,
#                 }

#                 scenario_instance = build_schema_data(schema, scenario_data, ScenarioInfo)
#                 validated_scenarios.append(scenario_instance)
#             except Exception as e:
#                 scenario_validation_errors.append(str(e))


#     if not scenario_validation_errors:
#         state.cognitive.extracted_all_scenario = True
#         state.cognitive.scenario_validation_errors = ""
#         state.cognitive.scenarios_to_generate = validated_scenarios
#     else:
#         state.cognitive.extracted_all_scenario = False
#         state.cognitive.scenario_validation_errors = (
#             "The following errors were detected for the scenarios you defined:\n- " + "\n- ".join(scenario_validation_errors)
#         )
#         state.cognitive.additional_output_information = [f"Extracted so far: {validated_scenarios}"]
#         state.cognitive.scenarios_to_generate = []

#     logger.info(
#         f"Extracted scenarios: {state.cognitive.scenarios_to_generate}, "
#         f"extracted_all_scenario: {state.cognitive.extracted_all_scenario}, "
#         f"scenario_validation_errors: {state.cognitive.scenario_validation_errors}"
#     )

#     state.add_trace("node_execution", node="extract_scenario", data={"extracted": state.cognitive.scenarios_to_generate,"extracted_all_scenario": state.cognitive.extracted_all_scenario,})
#     state.active_workflow = AgentState.Workflow.SCENARIO_CREATION
#     state.user_input = None

#     if state.cognitive.scenarios_to_generate:
#         state.waiting_for = AgentState.WaitingFor.SCENARIO_CONFIRMATION
#     else:
#         state.waiting_for = AgentState.WaitingFor.SCENARIO_INPUT

#     return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)   
def extract_scenario(state: AgentState) -> Command:
    logger.info("Entering extract_scenario")
    publish(state.session_id, "Extracting information from your input...")

    answer = extract_scenario_data(state)
    logger.info(f"Chatbot answer: {answer}")   
    
    parsed_answer = parse_llm_json(answer)
    scenarios = parsed_answer["scenarios"]
    modify_indexes = parsed_answer["modify_indexes"]
    # prevent keep showing sliders
    if modify_indexes and not (state.get_last_message().role == "user"):
        modify_indexes = False

    logger.info(f"Extracted scenario: {scenarios} + indexes {state.cognitive.scenario_validated_indexes}")  
   
    # assume only one scenario is extracted for now, we can iterate later if needed
    state.cognitive.scenario_extracted = {**(state.cognitive.scenario_extracted or {}), **(scenarios[0] if scenarios else {})}
    
    validated_scenarios: list[ScenarioInfo] = []
    scenario_validation_errors = []
    schema = ScenarioInfoSchema.default()

    if state.cognitive.scenario_extracted and state.cognitive.scenario_validated_indexes and not modify_indexes:
        try:
            scenario_data = {
                "title": state.cognitive.scenario_extracted.get("title"),
                "description": state.cognitive.scenario_extracted.get("description"),
                "indexes_to_change": state.cognitive.scenario_validated_indexes,
            }

            scenario_instance = build_schema_data(schema, scenario_data, ScenarioInfo)
            validated_scenarios.append(scenario_instance)
        except Exception as e:
            scenario_validation_errors.append(str(e))
            validated_scenarios: list[ScenarioInfo] = []

    if len(validated_scenarios) and not modify_indexes:
        logger.info("Extracted all")
        state.cognitive.extracted_all_scenario = True
        state.cognitive.scenario_validation_errors = ""
        state.cognitive.scenarios_to_generate = validated_scenarios
        state.sliders_data = None
    else:
        logger.info("Something is missing")
        state.cognitive.extracted_all_scenario = False
        if len(scenario_validation_errors):
            state.cognitive.scenario_validation_errors = (
                "The following errors were detected for the scenarios you defined:\n- " + "\n- ".join(scenario_validation_errors)
            )
        state.cognitive.additional_output_information = [f"Extracted so far: {state.cognitive.scenario_extracted}"]
        state.cognitive.scenarios_to_generate = []
        if not state.cognitive.scenario_displayed_ranges or modify_indexes or not state.cognitive.scenario_validated_indexes:
            state.cognitive.scenario_validated_indexes = {}
            state.cognitive.scenario_displayed_ranges = True
            state.sliders_data = get_sliders.invoke({})
        else:
            state.sliders_data = None

    logger.info(
        f"Extracted scenarios: {state.cognitive.scenarios_to_generate}, "
        f"extracted_all_scenario: {state.cognitive.extracted_all_scenario}, "
        f"scenario_validation_errors: {state.cognitive.scenario_validation_errors}"
    )

    state.add_trace("node_execution", node="extract_scenario", data={"extracted": state.cognitive.scenarios_to_generate,"extracted_all_scenario": state.cognitive.extracted_all_scenario,})
    state.active_workflow = AgentState.Workflow.SCENARIO_CREATION
    state.user_input = None

    if state.cognitive.scenarios_to_generate:
        state.waiting_for = AgentState.WaitingFor.SCENARIO_CONFIRMATION
    else:
        state.waiting_for = AgentState.WaitingFor.SCENARIO_INPUT

    return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

def parse_scenario_confirmation(state):
    return parse_confirmation(state, "SCENARIO")


def create_scenario(state: AgentState) -> AgentState:
    if state.cognitive.scenarios_to_generate:
        state.add_trace("node_execution", node="create_scenario", data={"to_generate": len(state.cognitive.scenarios_to_generate)})
        publish(state.session_id, "Creating scenario instance based on the extracted information")
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

        return Command(update=state, goto="create_scenario")
    else:
        state.resume_nome = {}
        state.active_workflow = None
        state.waiting_for = None
        state.reset_state(
            reset_listing=True,
            reset_new_problem=True,
            reset_new_proposal=True,
            reset_new_scenario=True,
            reset_errors=True,
            reset_context=False,
            reset_data=False
        )
        state.cognitive.messages_to_include = [get_message(MessageCode.SUCCESSFUL_INSTANCE_CREATION, instance="scenario")]
        state.cognitive.additional_output_information = []

        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)
    

################################################################33
# from app.utils.llm_reasoning import assess_scenario_strategy


# def decide_scenario_strategy(state: AgentState) -> AgentState:
#     logger.info("Deciding scenario generation strategy based on reasoning context.")
#     answer = assess_scenario_strategy(state).strip()

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
#         return Command(update=state, goto="new_scenario", graph=Command.PARENT)
#     if state.cognitive.next_action == "GENERATE_AGENTIC_SCENARIOS":
#         state.waiting_for = None
#         return Command(update=state, goto="generate_scenario_candidates", graph=Command.PARENT)
#     if state.cognitive.next_action == "ASK_USER_PREFERENCE":
#         state.active_workflow = AgentState.Workflow.PROBLEM_CREATION
#         state.waiting_for = AgentState.WaitingFor.SCENARIO_PREFERENCE
#         state.user_input = None
#         return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)
#     if state.cognitive.next_action == "NO_SCENARIOS":
#         state.waiting_for = None
#         state.cognitive.messages_to_include = [get_message(MessageCode.GENERAL_EXIT_MESSAGE)]
#         state.cognitive.additional_output_information = []

#         return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

#     raise ValueError(f"Invalid scenario strategy action: {state.cognitive.next_action}")