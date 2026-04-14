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
    to_log = True

    if state.cognitive.error_details:
        logger.error(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}")
        
        # Only write to file for unexpected/system errors, not request-level ones
        if to_log:
            with open("logs/errors.txt", "a+") as f:
                f.write(f"Error in node {state.cognitive.error_node}: {state.cognitive.error_details}\n")

        state.cognitive.additional_output_information = [
            f"Error details: {state.cognitive.error_details}"
        ]

    state.reset_state(reset_errors=False)
    state.cognitive.messages_to_include = [state.cognitive.error_details] if state.cognitive.error_details else ["Something went wrong, please try again later."]

    return Command(update=state, goto="generate_output_message")

# ---------------------------------------------------------------------------
# OUTPUT GENERATION
# ---------------------------------------------------------------------------

def generate_output_message_node(state: AgentState) -> Command:
    logger.info("Entering output generation")
    state = build_output_message(state)

    if state.cognitive.pending_actions and not state.waiting_for:
        return Command(update=state, goto="intent")

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

    state.cognitive.next_action = parse_confirmation_message(state) + cfg.suffix
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
