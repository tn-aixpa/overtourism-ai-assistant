from __future__ import annotations
# import re
import logging

from app.agent.state import AgentState
from app.utils.error_codes import GraphError
from app.tools.backend_tools import get_all_items

logger = logging.getLogger(__name__)

WORKFLOW_TO_INTENT = {
    AgentState.Workflow.PROBLEM_CREATION: "CREATE_NEW_PROBLEM",
    AgentState.Workflow.PROPOSAL_CREATION: "CREATE_NEW_PROPOSAL",
    AgentState.Workflow.SCENARIO_CREATION: "CREATE_NEW_SCENARIO",
    AgentState.Workflow.INTERACTION: "INTERACT_CONTEXT",
}


def get_available_entries_if_missing(state: AgentState) -> str:
    if not state.cognitive.available_entries:
        logger.info("Loading context information")
        available_entries = get_all_items.invoke({})
        state.cognitive.available_entries = available_entries
    return state

def build_output_message(state: AgentState) -> AgentState:
    from app.utils.llm_text_generation import generate_answer

    try:
        output_message = generate_answer(state)
    except Exception as e:
        print(f"Error {e}")
        output_message = "System error"
    state.add_assistant_message(
        output_message
    )

    print(output_message)

    return state

class RequestHandlingException(GraphError):
    """Exception raised when request handling fails."""
    def __init__(self, message: str):
        super().__init__(
            details=str(message)
        )