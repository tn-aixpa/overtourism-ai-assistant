import re
from .llm import llm_classify_confirmation

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