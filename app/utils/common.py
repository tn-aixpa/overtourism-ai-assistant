from __future__ import annotations

import re
from app.agent.state import AgentState
from app.utils.error_codes import GraphError


def parse_confirmation_message(state: AgentState) -> str:
    from app.utils.llm_reasoning import llm_classify_confirmation

    message = state.get_last_user_message().content
    CONFIRM = {"yes", "ok", "confirm", "sure", "go", "proceed"}
    EDIT = {"edit", "change", "modify", "adjust"}
    CANCEL = {"cancel", "interrupt", "quit", "stop", "no"}
    message = re.sub(r"[^\w\s]", "", message.lower())
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
    except:
        output_message = "System error"
    state.add_assistant_message(
        output_message
    )

    return state

class RequestHandlingException(GraphError):
    """Exception raised when request handling fails."""
    def __init__(self, message: str):
        super().__init__(
            details=str(message)
        )