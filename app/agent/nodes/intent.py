import logging
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm_reasoning import classify_intent
from app.utils.error_codes import ErrorCode, GraphError

logger = logging.getLogger(__name__)


def intent_node(state: AgentState) -> AgentState:
    logger.info("Entered INTENT_NODE")
    answer = classify_intent(state.get_last_user_message().content, state.get_reasoning_context())

    state.cognitive.next_action = answer
    logger.info(f"Detected intent: {answer}")
    state.add_trace("node_execution", node="intent_node", data={"intent": answer})
    return state
   
def route_from_intent(state: AgentState):
    logger.info(f"Routing based on intent: {state.cognitive.next_action}")
    state.add_trace("node_execution", node="route_from_intent", data={"intent": state.cognitive.next_action})
    action = state.cognitive.next_action

    if action == "INVALID":
        logger.error("Intent classified as INVALID → raising error")
        raise GraphError(ErrorCode.INVALID_REQUEST)

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

    raise GraphError(ErrorCode.REQUEST_ERROR)
    