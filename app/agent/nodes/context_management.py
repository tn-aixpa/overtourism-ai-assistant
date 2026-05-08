import logging
from langgraph.types import Command

from app.agent.events import publish
from app.agent.state import AgentState
from app.utils.llm_structured_extractions import get_context_activation_deactivation_list
from app.utils.llm import parse_llm_json
from app.tools.backend_tools import get_data_from_context
from app.utils.messages import get_message, MessageCode
from app.utils.common import RequestHandlingException, get_available_entries_if_missing
from app.config import SYSTEM_DESCRIPTION


logger = logging.getLogger(__name__)

def assess_context_request(state: AgentState) -> AgentState:
    logger.info("Entered assess_context_request node")
    publish(state.session_id, "Attemtpting to understand and apply context change request")

    state = get_available_entries_if_missing(state)

    available = state.cognitive.available_entries.get("all_ids", [])

    activation_deactivation_list = get_context_activation_deactivation_list(state)

    parsed = parse_llm_json(activation_deactivation_list)
    activate = set(parsed.get("activate", [])) & available
    deactivate = set(parsed.get("deactivate", [])) & available
    if (activate & deactivate):
        raise RequestHandlingException("Same context cannot be activated and deactivated at the same time")
    
    if not len(activate)+len(deactivate) > 0:
        raise RequestHandlingException("No valid context to activate or deactivate was provided")

    state.add_trace("node_execution", node="assess_context_request", data={"extracted": str(parsed)})
    state.cognitive.previous_context = state.cognitive.active_context
    if not activate and not deactivate:
        return state

    # Shortcuts to your data
    ids_dict = state.cognitive.available_entries.get("ids_dict", {})
    problems = ids_dict.get("problems", set())
    proposals = ids_dict.get("proposals", set())
    scenarios = ids_dict.get("scenarios", set())

    current_active = set(state.cognitive.active_context)

    # ---------------------------------------------------------------------------
    # Rule 1: Activating a PROBLEM_CREATION
    # Only one problem allowed → reset everything else
    # ---------------------------------------------------------------------------
    problem_activations = activate & problems
    if problem_activations:
        if len(problem_activations) > 1:
            raise RequestHandlingException("I can only activate one problem at a time, but I found multiple in your request")
        if len(activate) > len(problem_activations):
            raise RequestHandlingException("I am not sure about what context you want to use, can you please specify what context you want to explore?")

        selected_problem = next(iter(problem_activations))
        logger.info(f"Activating problem {selected_problem}, resetting context")

        state.cognitive.active_context_type = "problem"
        state.cognitive.active_context = [selected_problem]
        return state

    # ---------------------------------------------------------------------------
    # Rule 2: Activating a PROPOSAL
    # Only one proposal allowed → reset everything else
    # ---------------------------------------------------------------------------
    proposal_activations = activate & proposals
    if proposal_activations:
        if len(proposal_activations) > 1:
            raise RequestHandlingException("I can only activate one proposal at a time, but I found multiple in your request")
        if len(activate) > len(proposal_activations):
            raise RequestHandlingException("I am not sure about what context you want to use, can you please specify it?")

        selected_proposal = next(iter(proposal_activations))

        logger.info(f"Activating proposal {selected_proposal}, resetting context")

        state.cognitive.active_context_type = "proposal"
        state.cognitive.active_context = [selected_proposal]
        return state

    # ---------------------------------------------------------------------------
    # Rule 3: Activating SCENARIOS
    # Multiple allowed, but NOT with problems or proposals
    # ---------------------------------------------------------------------------
    scenario_activations = activate & scenarios
    if scenario_activations:
        logger.info(f"Activating scenarios {scenario_activations}, clearing other types")

        # Remove any problems/proposals from current context, remove also elements in deactivate
        current_active = current_active - problems - proposals - deactivate

        # Add new scenarios
        current_active |= scenario_activations

        state.cognitive.active_context_type = "scenario"
        state.cognitive.active_context = current_active
        return state

    # ---------------------------------------------------------------------------
    # Check if there is something to deactive + fallback
    # ---------------------------------------------------------------------------
    if deactivate:
        current_active -= deactivate

        if not current_active:
            state.cognitive.active_context_type = ""

        state.cognitive.active_context = current_active

    return state

def handle_context(state: AgentState) -> AgentState:
    logger.info("Entering handle_context node")
    if state.cognitive.active_context == state.cognitive.previous_context:
        return state
    
    extract_editable = (
        not isinstance(state.cognitive.editable_indexes, dict)
        or len(state.cognitive.editable_indexes) == 0
    )

    extracted_data = get_data_from_context.invoke({
        "context_type": state.cognitive.active_context_type,
        "context": list(state.cognitive.active_context),
        "relations": state.cognitive.available_entries["connections_dict"],
        "extract_editable": extract_editable
    })
    retrieved = extracted_data["retrieved"]
    editable_indexes = extracted_data["editable_indexes"]
    state.add_trace("node_execution", node="handle_context", data={"extracted": str(retrieved)})

    state.cognitive.context_data = retrieved

    if extract_editable:
        state.cognitive.editable_indexes = editable_indexes

    return state

def routing_after_context(state: AgentState) -> AgentState:
    state.add_trace("node_execution", node="routing_after_context")
    logger.info("Entering routing_after_context node")

    if not state.resume_nome:

        context = ",".join(state.cognitive.active_context)
        state.cognitive.messages_to_include = [get_message(MessageCode.CHANGED_CONTEXT, new_context=context)]
        state.cognitive.additional_output_information = [
            f"Active contex: {state.get_active_context_string()}",
            SYSTEM_DESCRIPTION
        ]

        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)
    
    else:
        node = state.resume_nome["node"]
        subgraph = state.resume_nome["subgraph"]
        return Command(update=state, goto=node, graph=subgraph)
