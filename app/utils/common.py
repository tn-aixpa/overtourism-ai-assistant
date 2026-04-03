import re
from app.agent.state import AgentState
from app.utils.llm_reasoning import llm_classify_confirmation
from app.utils.llm_text_generation import generate_answer

def parse_confirmation(message):
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
    return llm_classify_confirmation(message)

def to_state(result_dict) -> AgentState:
    return AgentState(**result_dict)

def build_output_message(state: AgentState) -> AgentState:
    output_message = generate_answer(
        state.get_last_user_message().content,
        state.user_lang,
        state.cognitive.messages_to_include,
        state.cognitive.additional_output_information
    )
    state.add_assistant_message(
        output_message
    )

    return state