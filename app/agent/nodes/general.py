import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.error_codes import get_error_message, ErrorCode
from app.utils.common import build_output_message

logger = logging.getLogger(__name__)

def error_recovery_node(state: AgentState) -> Command:
    code = getattr(state, "error_code", ErrorCode.REQUEST_ERROR)

    if state.cognitive.error_details:
        with open("logs/errors.txt", "a+") as f:
            logger.error(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}")
            f.write(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}\n")
        state.cognitive.additional_output_information = [f"Error details {state.cognitive.error_details}"]

    state.reset_state(reset_errors=False)

    state.cognitive.messages_to_include = [get_error_message(code)]

    return Command(update=state, goto="generate_output_message")

def generate_output_message_node(state: AgentState) -> Command:
    logger.info("Entering output generation")
    state = build_output_message(state)
    
    return Command(update=state, goto=END)

    #TODO add option for WAIT
    #TODO add ids replacement
