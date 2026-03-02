from langgraph.types import Command
from langgraph.graph import END

from ..state import AgentState
from app.utils.error_codes import get_error_message, ErrorCode

def error_recovery_node(state: AgentState) -> Command:
    code = getattr(state, "error_code", ErrorCode.REQUEST_ERROR)

    if state.error_details:
        with open("logs/errors.txt", "a+") as f:
            f.write(f"Error in node {state.error_node}: {state.error_details}\n")

    state.cognitive.next_action = None
    state.add_assistant_message(
        get_error_message(code, state.user_lang),
        get_error_message(code, "English")
    )

    return Command(update=state, goto=END)
