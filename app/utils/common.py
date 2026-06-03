from __future__ import annotations
import re
import logging

from app.agent.state import AgentState
from app.utils.error_codes import GraphError
from app.tools.backend_tools import get_problems

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
        available_entries = get_problems.invoke({})
        state.cognitive.available_entries = available_entries
    return state

def parse_confirmation_message(state: AgentState) -> str:
    from app.utils.llm_reasoning import llm_classify_confirmation

    message = state.get_last_user_message().content.lower()
    CONFIRM = {"yes", "ok", "okay", "confirm", "sure", "go", "proceed",
               "sì", "confermo", "certo", "vai", "procedi"}
    EDIT = {"edit", "change", "modify", "adjust",
            "modifica", "modificare", "cambia", "cambiare"}
    CANCEL = {"cancel", "interrupt", "quit", "stop", "no",
              "annulla", "cancella", "interrompi"}
    message = re.sub(r"[^\w\s]", "", message)
    tokens = set(message.split())

    scores = {
        "CONFIRM": len(tokens & CONFIRM),
        "EDIT": len(tokens & EDIT),
        "CANCEL": len(tokens & CANCEL),
    }

    best = max(scores, key=scores.get)

    # Strong signal threshold
    if scores[best] >= 1:
        return best

    # fallback to LLM classification
    return llm_classify_confirmation(state)

def to_state(result_dict) -> AgentState:
    return AgentState(**result_dict)

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