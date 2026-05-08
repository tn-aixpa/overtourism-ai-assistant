from langgraph.types import Command, interrupt
import logging

from app.agent.state import AgentState
from app.utils.common import build_output_message, WORKFLOW_TO_INTENT
from app.utils.llm_reasoning import extract_action_plan

logger = logging.getLogger(__name__)

def _wait_instructions(state: AgentState):
    waiting_for = state.waiting_for
    logger.info(f"Generating wait instructions. Waiting for: {waiting_for}")

    if waiting_for == AgentState.WaitingFor.PROBLEM_INPUT:
        instructions = state.cognitive.messages_to_include[0]
        additional_info = [state.cognitive.problem_info_to_extract.format_structure()]
        return instructions, additional_info

    if waiting_for == AgentState.WaitingFor.PROBLEM_CONFIRMATION:
        formatted_proposal = state.cognitive.problem_info_extracted.format_fields()
        return f"Do you want to proceed with the following problem?\n- {formatted_proposal}", []
        
    if waiting_for == AgentState.WaitingFor.PROPOSAL_INPUT:
        instructions = state.cognitive.messages_to_include[0]
        additional_info = [state.cognitive.proposal_info_to_extract.format_structure()]
        return instructions, additional_info

    if waiting_for == AgentState.WaitingFor.PROPOSAL_CONFIRMATION:
        formatted_proposal = state.cognitive.proposal_info_extracted.format_fields()
        return f"Do you want to proceed with the following proposal?\n- {formatted_proposal}", []

    if waiting_for == AgentState.WaitingFor.SCENARIO_INPUT:
        prefix = (state.cognitive.scenario_validation_errors + "\n") if state.cognitive.scenario_validation_errors else ""
        instructions = prefix + "Please, provide all required details to create a scenario."

        additional_info = [
            state.cognitive.scenario_info_to_extract.format_structure(),
            #f"Editable indexes: {state.cognitive.editable_indexes}"
        ]
        if not state.cognitive.scenario_validated_indexes:
            additional_info.append("Please use the sliders to set indexes to change")
    
        return instructions, additional_info

    if waiting_for == AgentState.WaitingFor.SCENARIO_CONFIRMATION:
        items = "\n- ".join(x.format_fields() for x in state.cognitive.scenarios_to_generate)
        return f"Do you want to proceed with the following scenarios?\n- {items}", []

    return "Please provide more details.", []


def wait_user_input_node(state: AgentState):
    """
    Single WAIT node for all workflows.
    - If no `state.user_input`, emit instructions + interrupt.
    - If `state.user_input` exists, route back to the active workflow.
    """
    logger.info("Entered WAIT_USER_INPUT node")
    waiting_for_value = state.waiting_for.value if state.waiting_for else None
    active_workflow_value = state.active_workflow.value if state.active_workflow else None

    if not state.user_input:
        logger.info("No user input detected → interrupting flow"
                    )
        instructions, additiona_info = _wait_instructions(state)
        state.cognitive.messages_to_include = [instructions]
        state.cognitive.additional_output_information.extend(additiona_info) 
        state = build_output_message(state)

        state.add_trace(
            "human_wait",
            node="WAIT_USER_INPUT",
            data={"waiting_for": waiting_for_value, "active_workflow": active_workflow_value, "instructions": instructions},
        )
        interrupt({"type": "WAIT_USER_INPUT", "waiting_for": waiting_for_value, "active_workflow": active_workflow_value})
        return state

    logger.info("User input received → resuming workflow")
    if not state.active_workflow:
        logger.warning("active_workflow is None when resuming — falling back to intent")
        return Command(update=state, goto=AgentState.Workflow.INTENT.value)
    expected_intent = WORKFLOW_TO_INTENT.get(state.active_workflow)
    detected_intents = extract_action_plan(state)
    if detected_intents[0] == "INVALID":
        # Ambiguous/confirmatory reply — stay in current workflow
        workflow = state.active_workflow.value if state.active_workflow else AgentState.Workflow.INTENT.value
        return Command(update=state, goto=workflow)

    if (
        expected_intent
        and detected_intents[0] not in ("INVALID", expected_intent)
    ):
        logger.info(
            "Intent switched while waiting. "
            f"Expected={expected_intent}, detected={detected_intents[0]}"
        )
        state.suspended_workflow = state.active_workflow
        state.suspended_waiting_for = state.waiting_for
        state.active_workflow = None
        state.waiting_for = None
        return Command(update=state, goto="intent")

    workflow = state.active_workflow.value if state.active_workflow else AgentState.Workflow.INTENT.value
    return Command(update=state, goto=workflow)


def resume_router(state: AgentState):
    if state.waiting_for:
        return "WAIT_USER_INPUT"
    return "intent"