import logging
import json
from langgraph.graph import END
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.error_codes import ErrorCode, GraphError
from app.utils.llm_reasoning import get_context_activation_deactivation_list
from app.tools.backend_tools import get_data_from_context, get_problems
from app.utils.messages import get_message, MessageCode


logger = logging.getLogger(__name__)

def assess_context_request(state: AgentState) -> AgentState:
    logger.info("Entered assess_context_request node")

    if not state.downloaded_data:
        logger.info("Loading context information")
        downloaded_data = get_problems.invoke({})
        state.downloaded_data = downloaded_data


    activation_deactivation_list = get_context_activation_deactivation_list(
        state.get_last_message(),
        state.get_reasoning_context(),
        state.cognitive.active_context,
        state.downloaded_data.get("all_ids", [])
    )

    try:
        parsed = json.loads(activation_deactivation_list)
        activate = set(parsed.get("activate", []))
        deactivate = set(parsed.get("deactivate", []))
    except Exception as e:
        raise GraphError(ErrorCode.INVALID_CONTEXT, f"Error determining context: {e}")
    
    state.add_trace("node_execution", node="assess_context_request", data={"extracted": str(parsed)})
    state.cognitive.previous_context = state.cognitive.active_context
    if not activate and not deactivate:
        return state

    # Shortcuts to your data
    ids_dict = state.downloaded_data.get("ids_dict", {})
    problems = ids_dict.get("problems", set())
    proposals = ids_dict.get("proposals", set())
    scenarios = ids_dict.get("scenarios", set())

    current_active = set(state.cognitive.active_context)

    # ---------------------------------------------------------------------------
    # Rule 1: Activating a PROBLEM
    # Only one problem allowed → reset everything else
    # ---------------------------------------------------------------------------
    problem_activations = activate & problems
    if problem_activations:
        if len(problem_activations) > 1:
            raise GraphError(ErrorCode.INVALID_CONTEXT, "I tried to activete a problem but more than one was provided")
        if len(activate) > len(problem_activations):
            raise GraphError(ErrorCode.INVALID_CONTEXT, "I am not sure about what context you want to use, can you please specify what context you want to explore?")
   
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
            raise GraphError(ErrorCode.INVALID_CONTEXT, "I tried to activete a proposal but more than one was provided")
        if len(activate) > len(problem_activations):
            raise GraphError(ErrorCode.INVALID_CONTEXT, "I am not sure about what context you want to use, can you please specify it?")
   
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
        "relations": state.downloaded_data["connections_dict"],
        "extract_editable": extract_editable
    })
    retrieved = extracted_data["retrieved"]
    editable_indexes = extracted_data["editable_indexes"]
    state.add_trace("node_execution", node="handle_context", data={"extracted": str(retrieved)})

    state.cognitive.data = retrieved

    if extract_editable:
        state.cognitive.editable_indexes = editable_indexes

    return state

def routing_after_context(state: AgentState) -> AgentState:
    state.add_trace("node_execution", node="routing_after_context")
    logger.info("Entering routing_after_context node")

    if state.cognitive.next_action == "CONTEXT_MANAGEMENT":
        context = ",".join(state.cognitive.active_context)
        state.add_assistant_message(
            get_message(MessageCode.CHANGED_CONTEXT, state.user_lang, new_context=context),
            get_message(MessageCode.CHANGED_CONTEXT, "English", new_context=context)
        )
        return Command(update=state, goto=END)
    
    else:
        #TODO
        pass
    return state