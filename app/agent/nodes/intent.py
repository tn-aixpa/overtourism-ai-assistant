import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException
from app.utils.llm_reasoning import extract_action_plan
from app.utils.messages import MessageCode, get_message
from app.utils.state_variables import VALID_INTENTS
from app.agent.events import publish
from app.config import SYSTEM_DESCRIPTION


logger = logging.getLogger(__name__)


def _is_resume_request(state: AgentState) -> bool:
    if not state.suspended_workflow:
        return False
    last_user_message = state.get_last_user_message()
    if not last_user_message:
        return False
    message = last_user_message.content.lower()
    return any(token in message for token in ("resume", "continue", "go back", "pick up"))

def intent_node(state: AgentState) -> AgentState:
    state.reset_state(reset_errors=True, reset_context=False, reset_data=False)
    publish(state.session_id, "Assessing user intent")
    logger.info("Entered INTENT_NODE")

    if _is_resume_request(state):
        state.active_workflow = state.suspended_workflow
        state.waiting_for = state.suspended_waiting_for
        state.suspended_workflow = None
        state.suspended_waiting_for = None
        answer = state.active_workflow.value

    elif state.cognitive.pending_actions:
        answer = state.cognitive.pending_actions.pop(0)

    else:
        plan = extract_action_plan(state)
        answer = plan[0]
        if len(plan) > 1:
            state.cognitive.pending_actions = plan[1:]

    state.cognitive.next_action = answer
    logger.info(f"Detected intent: {answer}")
    state.add_trace("node_execution", node="intent_node", data={"intent": answer})
    return state
   
def route_from_intent(state: AgentState):
    logger.info(f"Routing based on intent: {state.cognitive.next_action}")
    state.add_trace("node_execution", node="route_from_intent", data={"intent": state.cognitive.next_action})
    action = state.cognitive.next_action

    if not action in VALID_INTENTS:
        raise RequestHandlingException(f"Invalid intent detected: {action}")

    if action == "INVALID":
        logger.error("Intent classified as INVALID → raising error")
        state.cognitive.messages_to_include = [get_message(MessageCode.INVALID_REQUEST)]
        state.cognitive.additional_output_information = []
        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

    if action == "INTERACT_CONTEXT":
        return Command(update=state, goto="interaction", graph=Command.PARENT)

    if action == "CREATE_NEW_PROBLEM":
        return Command(update=state, goto="new_problem", graph=Command.PARENT)
    
    if action == "CREATE_NEW_PROPOSAL":
        return Command(update=state, goto="new_proposal", graph=Command.PARENT)
    
    if action == "CREATE_NEW_SCENARIO":
        return Command(update=state, goto="new_scenario", graph=Command.PARENT)

    if action == "LIST_AVAILABLE":
        return Command(update=state, goto="list_available", graph=Command.PARENT)

    if action == "CONTEXT_MANAGEMENT":
        return Command(update=state, goto="context_management", graph=Command.PARENT)
    
    if action == "ASSISTANT_CAPABILITIES":
        state.cognitive.messages_to_include = []
        state.cognitive.additional_output_information = [
            f"Active contex: {state.get_active_context_string()}",
            SYSTEM_DESCRIPTION,
            state.cognitive.problem_info_to_extract.format_structure(),
            state.cognitive.proposal_info_to_extract.format_structure(),
            state.cognitive.scenario_info_to_extract.format_structure()
        ]

        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

    if action in (
        AgentState.Workflow.PROBLEM_CREATION.value,
        AgentState.Workflow.PROPOSAL_CREATION.value,
        AgentState.Workflow.SCENARIO_CREATION.value,
        AgentState.Workflow.INTERACTION.value,
    ):
        return Command(update=state, goto=action, graph=Command.PARENT)

    