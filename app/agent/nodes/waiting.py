from langgraph.types import Command, interrupt
import logging

from app.agent.state import AgentState
from app.utils.common import translate_from_eng
from app.utils.common import build_output_message

logger = logging.getLogger(__name__)

def _wait_instructions(state: AgentState):
    waiting_for = state.waiting_for
    logger.info(f"Generating wait instructions. Waiting for: {waiting_for}")

    if waiting_for == AgentState.WaitingFor.PROBLEM_INPUT:
        missing = [
            k
            for k, v in state.cognitive.problem_info_to_extract.items()
            if v.get("required") and k not in state.cognitive.extracted_problem_info
        ]
        if missing:
            return "To correctly create the new problem, please provide the missing information:\n- " + "\n- ".join(missing), []
        
        return "To correctly create the new problem, please provide the missing information.", []

    if waiting_for == AgentState.WaitingFor.PROBLEM_CONFIRMATION:
        extracted = "\n- ".join(f"{k}: {v}" for k, v in state.cognitive.extracted_problem_info.items())
        return f"These are the information I extracted:\n- {extracted}.\n\nDo you want to proceed with the creation fo this problem?", []

    if waiting_for == AgentState.WaitingFor.SCENARIO_PREFERENCE:
        return (
            "The problem was successfully created. Do you want to create scenarios for this problem? "
            "If so, do you have specific scenarios in mind or would you like the system to generate some based on the problem information?"
        ), []
    
    if waiting_for == AgentState.WaitingFor.PROPOSAL_INPUT:
        instructions = state.cognitive.messages_to_include[0]
        return instructions, []

    if waiting_for == AgentState.WaitingFor.PROPOSAL_CONFIRMATION:
        formatted_proposal = state.cognitive.extracted_proposal_info.format_fields()
        return f"Do you want to proceed with the following proposal?\n- {formatted_proposal}", []

    if waiting_for == AgentState.WaitingFor.SCENARIO_INPUT:
        prefix = (state.cognitive.validation_errors + "\n") if state.cognitive.validation_errors else ""
        instructions = prefix + "Please, provide all required details to create a scenario."

        additional_info = [f"Editable indexes: {state.cognitive.editable_indexes}"]
    
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
    workflow = state.active_workflow.value if state.active_workflow else AgentState.Workflow.INTENT.value
    return Command(update=state, goto=workflow)


def resume_router(state: AgentState):
    if state.waiting_for:
        return "WAIT_USER_INPUT"
    return "intent"