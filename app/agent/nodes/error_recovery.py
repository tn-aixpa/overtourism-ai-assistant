from datetime import datetime
from langgraph.types import Command
from langgraph.graph import END

from ..state import AgentState, ConversationMessage
from app.utils.error_codes import get_error_message, ErrorCode

def error_recovery_node(state: AgentState) -> Command:
    code = getattr(state, "error_code", ErrorCode.REQUEST_ERROR)

    if state.error_details:
        with open("logs/errors.txt", "a+") as f:
            f.write(f"{state.error_details}\n")

    error_message = get_error_message(code, state.user_lang)

    state.cognitive.next_action = None

    state.conversation.append(
        ConversationMessage(
            role="assistant",
            content=error_message,
            timestamp=datetime.now()
        )
    )
    return Command(update=state, goto=END)
