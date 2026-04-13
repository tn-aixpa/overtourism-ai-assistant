import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException
from app.utils.llm_reasoning import classify_intent
from app.utils.messages import MessageCode, get_message
from app.utils.state_variables import VALID_INTENTS
from app.agent.events import publish


logger = logging.getLogger(__name__)


def intent_node(state: AgentState) -> AgentState:
    state.reset_state(reset_errors=True, reset_context=False, reset_data=False)
    
    publish(state.session_id, "Assessing user intent")
    logger.info("Entered INTENT_NODE")
    answer = classify_intent(state)

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
            state.cognitive.allowed_operations
        ]

        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

    