from dataclasses import dataclass
from typing import Optional
import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.error_codes import get_error_message, ErrorCode
from app.utils.messages import get_message, MessageCode
from app.utils.common import build_output_message
from app.utils.common import parse_confirmation_message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ERROR RECOVERY
# ---------------------------------------------------------------------------

def error_recovery_node(state: AgentState) -> Command:
    logger.info("Entering error recovery node")
    code = getattr(state, "error_code", ErrorCode.REQUEST_ERROR)

    if state.cognitive.error_details:
        with open("logs/errors.txt", "a+") as f:
            logger.error(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}")
            f.write(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}\n")
        state.cognitive.additional_output_information = [f"Error details {state.cognitive.error_details}"]

    state.reset_state(reset_errors=False)

    state.cognitive.messages_to_include = [get_error_message(code)]

    return Command(update=state, goto="generate_output_message")

# ---------------------------------------------------------------------------
# OUTPUT GENERATION
# ---------------------------------------------------------------------------

def generate_output_message_node(state: AgentState) -> Command:
    logger.info("Entering output generation")
    state = build_output_message(state)
    
    return Command(update=state, goto=END)

# ---------------------------------------------------------------------------
# CONFIRMATION PARSING
# ---------------------------------------------------------------------------

@dataclass
class ConfirmationConfig:
    suffix: str
    workflow: AgentState.Workflow
    waiting_for: AgentState.WaitingFor
    confirm_goto: str
    confirm_graph: Optional[str]   # None means stay in current graph
    edit_goto: str
    edit_graph: Optional[str]


CONFIRMATION_CONFIGS = {
    "PROBLEM": ConfirmationConfig(
        suffix="_PROBLEM",
        workflow=AgentState.Workflow.PROBLEM_CREATION,
        waiting_for=AgentState.WaitingFor.PROBLEM_CONFIRMATION,
        confirm_goto="create_problem",
        confirm_graph=None,
        edit_goto="extract_problem",
        edit_graph=Command.PARENT,
    ),
    "PROPOSAL": ConfirmationConfig(
        suffix="_PROPOSAL",
        workflow=AgentState.Workflow.PROPOSAL_CREATION,
        waiting_for=AgentState.WaitingFor.PROPOSAL_CONFIRMATION,
        confirm_goto="create_proposal",
        confirm_graph=None,
        edit_goto="extract_proposal",
        edit_graph=None,
    ),
    "SCENARIO": ConfirmationConfig(
        suffix="_SCENARIO",
        workflow=AgentState.Workflow.SCENARIO_CREATION,
        waiting_for=AgentState.WaitingFor.SCENARIO_CONFIRMATION,
        confirm_goto="create_scenario",
        confirm_graph=None,
        edit_goto="extract_scenario",
        edit_graph=None,
    ),
}


def parse_confirmation(state: AgentState, context: str) -> Command:
    """
    Unified confirmation parser.
    context: one of "PROBLEM", "PROPOSAL", "SCENARIO"
    """
    cfg = CONFIRMATION_CONFIGS[context]
    logger.info(f"Entering parse_confirmation [{context}]")

    message = state.get_last_user_message().content
    state.cognitive.next_action = parse_confirmation_message(message) + cfg.suffix
    logger.info(f"Parsed user confirmation: {state.cognitive.next_action}")
    state.add_trace("node_execution", node="parse_confirmation",
                    data={"next_action": state.cognitive.next_action, "context": context})

    # WAIT — needs more input before deciding
    if state.cognitive.next_action == f"WAIT_CONFIRMATION{cfg.suffix}":
        state.active_workflow = cfg.workflow
        state.waiting_for = cfg.waiting_for
        state.user_input = None
        return Command(update=state, goto="WAIT_USER_INPUT", graph=Command.PARENT)

    # CONFIRM — proceed to creation/execution
    if state.cognitive.next_action == f"CONFIRM{cfg.suffix}":
        state.waiting_for = None
        state.user_input = None
        kwargs = {"goto": cfg.confirm_goto}
        if cfg.confirm_graph:
            kwargs["graph"] = cfg.confirm_graph
        return Command(update=state, **kwargs)

    # CANCEL — exit the workflow entirely
    if state.cognitive.next_action in (f"CANCEL{cfg.suffix}", "CANCEL_PROPOSAL"):
        state.waiting_for = None
        state.user_input = None
        state.active_workflow = None
        state.cognitive.messages_to_include = [get_message(MessageCode.GENERAL_EXIT_MESSAGE)]
        state.cognitive.additional_output_information = []
        return Command(update=state, goto="generate_output_message", graph=Command.PARENT)

    # EDIT (fallthrough)
    state.waiting_for = None
    state.user_input = None
    kwargs = {"goto": cfg.edit_goto}
    if cfg.edit_graph:
        kwargs["graph"] = cfg.edit_graph
    return Command(update=state, **kwargs)





def temp_node(state: AgentState) -> Command:
    from app.utils.temp_chart import generate_chart
    # LOAD DATA
    # from app.tools.backend_tools import get_data_from_context, get_problems

    # logger.info("Entering temp node")

    # # Step1
    # logger.info("Step 1: Loading context information")
    # available_entries = get_problems.invoke({})
    # state.cognitive.available_entries = available_entries

    # logger.info("Step 2: activate context and get data")

    # extracted_data = get_data_from_context.invoke({
    #     "context_type": "scenario",
    #     "context": ["model_0"],
    #     "relations": state.cognitive.available_entries["connections_dict"],
    #     "extract_editable": True
    # })
    # retrieved = extracted_data["retrieved"]
    # editable_indexes = extracted_data["editable_indexes"]
    # state.cognitive.editable_indexes = editable_indexes

    # state.cognitive.context_data = retrieved

    # logger.info("Step 3: build output message")

    if "plot" in state.get_last_message().content.lower():
        state.chart_data = generate_chart("tourists_excursionists")
        state.add_assistant_message("Here is the requested graph")
    elif "load" in state.get_last_message().content.lower():
        state.chart_data = generate_chart("tourist_load")
        state.add_assistant_message("Here is the requested graph")
    elif "bar" in state.get_last_message().content.lower():
        state.chart_data = generate_chart("comparison_bar")
        state.add_assistant_message("Here is the requested graph")
    else:
        state.add_assistant_message("Success")

    return Command(update=state, goto=END)