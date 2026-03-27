import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.error_codes import get_error_message, ErrorCode
from app.utils.llm_text_generation import generate_answer

logger = logging.getLogger(__name__)

def error_recovery_node(state: AgentState) -> Command:
    code = getattr(state, "error_code", ErrorCode.REQUEST_ERROR)

    if state.cognitive.error_details:
        with open("logs/errors.txt", "a+") as f:
            logger.error(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}")
            f.write(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}\n")

    state.cognitive.next_action = None
    state.add_assistant_message(
        get_error_message(code, state.user_lang),
        get_error_message(code, "English")
    )

    return Command(update=state, goto=END)

def reset_state(state: AgentState, reset_context=True, reset_data=True) -> AgentState:
    state.waiting_for = None
    state.user_input = None
    state.cognitive.error_code = ""
    state.cognitive.error_node = ""
    state.cognitive.error_details = ""
    state.cognitive.messages_to_include = []

    # Reset cognitive
    state.cognitive.elements_to_list = []
    state.cognitive.filter_list_by = ""
    state.cognitive.partial_list = {}
    state.cognitive.problem_info_to_extract = {}
    state.cognitive.extracted_problem_info = {}
    state.cognitive.extracted_all_problem = False
    state.cognitive.scenario_info_to_extract = {}
    state.cognitive.extracted_all_scenario = False
    state.cognitive.scenarios_to_generate = []
    state.cognitive.validation_errors = ""
    state.cognitive.selected_roles = []
    state.cognitive.expert_answers = {}

    if reset_context:
        state.cognitive.active_context_type = ""
        state.cognitive.active_context = []
        state.cognitive.previous_context = []

    if reset_data:
        state.cognitive.context_data = {}
        state.cognitive.editable_indexes = {}
        state.cognitive.available_entries = {}

    return state

def generate_output_message(state: AgentState) -> Command:
    output_message = generate_answer(
        state.get_last_user_message().content_en,
        state.user_lang,
        state.cognitive.messages_to_include,
        state.cognitive.additional_output_information
    )
    state.add_assistant_message(
            output_message,
            output_message
        )

    return Command(update=state, goto=END)

    #TODO add option for WAIT
    #TODO add ids replacement
