import logging
import ast
from langgraph.graph import  END
from langgraph.types import Command

from app.agent.state import AgentState
from app.utils.llm_structured_extractions import assess_what_to_list
from app.utils.llm_text_generation import get_list_message, translate

from app.utils.error_codes import get_error_message, ErrorCode
from app.tools.backend_tools import get_problems

logger = logging.getLogger(__name__)


def assess_list(state: AgentState) -> AgentState:
    logger.info("Entered ASSESS_LIST")
    active_context = state.cognitive.active_context[0] if state.cognitive.active_context_type in ["problem", "proposal"] else None
    raw_output = assess_what_to_list(
        state.get_last_user_message().content_en,
        state.get_reasoning_context(),
        active_context
    ).strip()
    logger.info(f"Raw output: {raw_output}")

    ALLOWED = ["problems", "proposals", "scenarios"]
    try:
        extracted = ast.literal_eval(raw_output)

        if not isinstance(extracted, dict):
            raise ValueError("Output is not a valid dict")

        extracted_to_list = extracted.get("to_list", [])
        extracted_subject = extracted.get("subject", None)

        if not isinstance(extracted_to_list, list) or not all(isinstance(i, str) for i in extracted_to_list):
            raise ValueError("to_list is not a valid list of strings")

        to_list = [item for item in ALLOWED if item in set(extracted_to_list)]
        subject = extracted_subject if isinstance(extracted_subject, str) else None

        logger.info(f"Final to_list: {to_list}, subject: {subject}")

    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        to_list = []
        subject = None

    if not len(to_list):
        state.add_assistant_message(
            get_error_message(ErrorCode.NOTHING_TO_LIST),
            get_error_message(ErrorCode.NOTHING_TO_LIST, state.user_lang)
        )
        return Command(update=state, goto=END)

    state.cognitive.elements_to_list = to_list
    state.cognitive.filter_list_by = subject  # store the extracted subject

    state.add_trace("node_execution", node="assess_list", data={"to_list": to_list, "subject": subject})
    return state

def get_list(state: AgentState) -> AgentState:

    if not state.cognitive.available_entries:
        available_entries = get_problems.invoke({})
        state.cognitive.available_entries = available_entries

    subject = state.cognitive.filter_list_by
    allowed_set = None  # will stay None if no filtering is needed

    if subject:
        connections_dict = state.cognitive.available_entries["connections_dict"]
        allowed_entries = []

        if subject in connections_dict["problem_to_proposals"]:
            connected_proposals = connections_dict["problem_to_proposals"][subject]
            allowed_entries.extend(connected_proposals)

            for proposal in connected_proposals:
                allowed_entries.extend(
                    connections_dict["proposal_to_scenarios"].get(proposal, [])
                )

        if subject in connections_dict["proposal_to_scenarios"]:
            allowed_entries.extend(
                connections_dict["proposal_to_scenarios"][subject]
            )

        # Convert to set for faster membership checks
        allowed_set = set(allowed_entries)

        logger.info(
            f"For subject {subject} the allowed entries are {allowed_entries}"
        )

    state.cognitive.partial_list = {}

    for to_list in state.cognitive.elements_to_list:
        full_list = state.cognitive.available_entries["ids_dict"][to_list]

        if allowed_set is not None:
            filtered_list = [el for el in full_list if el in allowed_set]
            state.cognitive.partial_list[to_list] = filtered_list
        else:
            state.cognitive.partial_list[to_list] = full_list

    state.add_trace(
        "node_execution",
        node="get_list",
        data={"retrieved": state.cognitive.partial_list},
    )

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
    