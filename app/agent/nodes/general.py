import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.common import build_output_message

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

    state.cognitive.messages_to_include = [state.cognitive.error_details] if state.cognitive.error_details else ["Something went wrong, please try again later."]
    state.reset_state(
            reset_listing=True,
            reset_new_problem=True,
            reset_new_proposal=True,
            reset_new_scenario=True,
            reset_errors=True,
            reset_context=False,
            reset_data=False
        )

    return Command(update=state, goto="generate_output_message")

# ---------------------------------------------------------------------------
# OUTPUT GENERATION
# ---------------------------------------------------------------------------

def generate_output_message_node(state: AgentState) -> Command:
    logger.info("Entering output generation")

    # If there's a tool result and no messages prepared yet, build them from the result
    if state.cognitive.tool_result and not state.cognitive.messages_to_include:
        state.cognitive.messages_to_include = _build_messages_from_tool_result(
            state.cognitive.selected_tool,
            state.cognitive.tool_result,
        )

    state = build_output_message(state)

    state.cognitive.messages_to_include = []
    state.cognitive.additional_output_information = []
    state.cognitive.tool_result = None

    return Command(update=state, goto=END)


def _build_messages_from_tool_result(tool_name: str, tool_result: dict) -> list[str]:
    """Translate a tool result into messages for the output generator."""

    if not tool_result.get("success", True):
        error = tool_result.get("error", "An unknown error occurred.")
        return [f"The operation failed: {error}"]

    # Unwrap the inner output dict
    output = tool_result.get("output", tool_result)

    match tool_name:

        case "get_system_capabilities":
            return [output.get("system_description", "System description unavailable.")]

        case "list_problems":
            return [f"Here are the available items: {output}"]

        case "set_active_context":
            return [output.get("message", "Context updated successfully.")]

        case "get_context_details":
            return [f"Here are the requested details: {output}"]

        case "extract_problem_details" | "extract_proposal_details" | "extract_scenario_details":
            return [output.get("error", "Extraction completed.")]

        case "create_problem" | "create_proposal" | "create_scenario":
            return [f"Created successfully: {output}"]

        case "interact_with_context":
            return [output.get("message", str(output))]

        case _:
            return [str(output)]