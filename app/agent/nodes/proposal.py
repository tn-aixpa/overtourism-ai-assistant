import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm_structured_extractions import extract_proposal_data
from app.utils.llm import parse_llm_json
from app.agent.nodes.general import parse_confirmation
from app.utils.messages import get_message, MessageCode
from app.utils.error_codes import get_error_message, ErrorCode
from app.tools.backend_tools import create_proposal_instance
from app.tools.backend_tools_temp import get_RelatedScenario
from app.utils.backend_integration_classes import ProposalInfoSchema, ProposalInfo, build_schema_data
from app.config import BASE_SCENARIO_ID

logger = logging.getLogger(__name__)

def assert_active_problem(state: AgentState) -> Command:
    logger.info("Checking if there is an active problem")
    state.add_trace("node_execution", node="assert_active_problem")

    if state.cognitive.active_context_type == "problem":
        state.resume_nome = {}
        return Command(update=state, goto="extract_proposal")

    # TODO: when multi-action is implemented remove this resume, keep only output message
    logger.info("No active prposal, asking user to activate it")
    state.resume_nome = {
        "node": "new_proposal",
        "subgraph": Command.PARENT
    }

    state.cognitive.messages_to_include = [get_error_message(ErrorCode.INVALID_CONTEXT)]
    state.cognitive.additional_output_information = [
        f"Active contex: {state.get_active_context_string()}",
        state.cognitive.allowed_operations
    ]
    if state.cognitive.active_context_type == "":
        if state.cognitive.available_entries:
            available_problems = state.cognitive.available_entries["ids_dict"]["problems"]
            state.cognitive.additional_output_information.append(
                "Available problems are: " + ", ".join(available_problems) 
            )

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)


def extract_proposal(state: AgentState):
    logger.info("Entering extract_proposal")

    ids_dict = state.cognitive.available_entries.get("ids_dict", {})
    available_scenarios = ids_dict.get("scenarios", set())
    atttachments_list = []

    answer = extract_proposal_data(
        state.get_reasoning_context(),
        state.cognitive.proposal_info_to_extract,
        available_scenarios,
        atttachments_list
    )


    logger.info(f"Chatbot answer: {answer}")   
    assert "Error connecting to chatbot" not in answer
    
    proposal = parse_llm_json(answer)

    logger.info(f"Extracted proposal: {proposal}")   
    
    schema = ProposalInfoSchema.default()

    try:
        state.cognitive.proposal_info_extracted = build_schema_data(schema, proposal, ProposalInfo)
        state.cognitive.extracted_all_proposal = True
    except Exception as e:
        state.cognitive.messages_to_include = [str(e)]
        state.cognitive.proposal_info_extracted = None
        state.cognitive.extracted_all_proposal = False

    state.add_trace("node_execution", node="extract_proposal", data={"extracted": state.cognitive.proposal_info_extracted ,"extracted_all_proposal": state.cognitive.extracted_all_proposal})
    state.active_workflow = AgentState.Workflow.PROPOSAL_CREATION
    state.user_input = None

    if state.cognitive.extracted_all_proposal:
        state.waiting_for = AgentState.WaitingFor.PROPOSAL_CONFIRMATION
    else:
        state.waiting_for = AgentState.WaitingFor.PROPOSAL_INPUT

    return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

def parse_proposal_confirmation(state):
    return parse_confirmation(state, "PROPOSAL")   

def create_proposal(state: AgentState) -> AgentState:
    
    state.add_trace("node_execution", node="create_proposal")

    proposal = state.cognitive.proposal_info_extracted
    logger.info(f"Creating instance for proposal: {proposal}")
    
    problem_id = state.cognitive.active_context[0]

    # TODO: it would be nice to modify the call for related scenarios
    # Currently related_scenarios=[RelatedScenario(scenario_id='model_0', scenario_name='Scenario base', scenario_description=None, index_diffs=None)]
    related_scenarios_ids = proposal.connected_scenarios if proposal.connected_scenarios is not None else []
    if not BASE_SCENARIO_ID in related_scenarios_ids:
        related_scenarios_ids.append(BASE_SCENARIO_ID)

    extracted_data = get_RelatedScenario.invoke({
        "scenario_ids": related_scenarios_ids,
    })
    related_scenarios = extracted_data
    
    payload = {
        # "proposal_id": "string",
        # "updated": "string",
        # "created": "string",
        "proposal_title": proposal.title,
        "proposal_description": proposal.description,
        "resources": [proposal.related_data] if proposal.related_data else [],
        "context": proposal.context_conditions or None,
        "impact": proposal.potential_impact or None,
        "status": "draft",
        "related_scenarios": related_scenarios
    }

    # remove empty fields (recommended)
    payload = {k: v for k, v in payload.items() if v not in [None, "", [], {}]}

    result = create_proposal_instance.invoke({
        "problem_id": problem_id,
        "payload": payload,
    })


    logger.info(result)

    state.resume_nome = {}
    state.active_workflow = None
    state.cognitive.messages_to_include = [get_message(MessageCode.SUCCESS_PROPOSAL)]
    state.cognitive.additional_output_information = []

    #TODO: decide if we want to activate this proposal or ask the user if he wants to activate it

    return Command(update=state, goto="generate_output_message", graph=Command.PARENT)