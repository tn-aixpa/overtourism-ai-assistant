import logging
import ast
from langgraph.graph import  END
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm_reasoning import assess_what_to_list
from app.utils.llm_text_generation import get_list_message, translate

from app.utils.error_codes import get_error_message, ErrorCode
from app.tools.backend_tools import get_problems

logger = logging.getLogger(__name__)


def assess_list(state: AgentState) -> AgentState:
    logger.info("Entered ASSESS_LIST")
    raw_output = assess_what_to_list(state.get_last_user_message().content_en).strip()

    ALLOWED = ["problems", "proposals", "scenarios"]
    try:
        extracted_to_list = ast.literal_eval(raw_output)

        # Validate it's actually a list of strings
        if not isinstance(extracted_to_list, list) or not all(isinstance(i, str) for i in extracted_to_list):
            raise ValueError("Output is not a valid list of strings")
               
        # Normalize: filter + deduplicate + order
        to_list = [
            item for item in ALLOWED
            if item in set(extracted_to_list)
        ]

        logger.info(f"Final: {to_list}")

    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        to_list = []

    if not len(to_list):
        state.add_assistant_message(get_error_message(ErrorCode.NOTHING_TO_LIST), get_error_message(ErrorCode.NOTHING_TO_LIST, state.user_lang))
        return Command(update=state, goto=END)
    
    state.cognitive.elements_to_list = to_list

    state.add_trace("node_execution", node="assess_list", data={"to_list": to_list})
    logger.info(f"Extracted elements to list: {raw_output}")

    return state

def get_list(state: AgentState) -> AgentState:

    if not state.downloaded_data:
        downloaded_data = get_problems.invoke({})
        state.downloaded_data = downloaded_data

    state.cognitive.partial_list = {}
    for to_list in state.cognitive.elements_to_list:
        state.cognitive.partial_list[to_list] = state.downloaded_data["ids_dict"][to_list]

    state.add_trace("node_execution", node="get_list", data={"retrieved": state.cognitive.partial_list})
    return state

def generate_answer(state: AgentState) -> AgentState:
    answer = get_list_message(state.cognitive.partial_list)
    state.cognitive.partial_list = {}
    state.cognitive.elements_to_list = []

    assert "Error connecting to chatbot" not in answer

    logger.info(f"Generated answer: {answer}")
    state.add_trace("node_execution", node="generate_answer", data={"retrieved": answer})

    #TODO: handle this better for when using localized names for elements
    state.add_assistant_message(answer, translate(answer, "English", state.user_lang))

    return state
    