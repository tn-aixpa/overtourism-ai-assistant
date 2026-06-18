import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.common import build_output_message
from app.utils.common import RequestHandlingException
from app.utils.error_codes import GraphError


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SAFE NODE WRAPPERS
# ---------------------------------------------------------------------------

def add_safe_node(graph, name, fn):
    graph.add_node(name, safe(fn, name))

from langgraph.errors import GraphInterrupt

def safe(node_fn, node_name):
    def _safe(state):
        try:
            return node_fn(state)

        except GraphInterrupt as gi:
            raise gi

        except RequestHandlingException as rhe:
            # Custom behaviour: no errors.txt logging, just surface to user
            logger.warning(f"Request handling error in node {node_name}: {rhe}")
            state.cognitive.error_details = str(rhe)
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

        except GraphError as ge:
            logger.warning(f"GraphError in node {node_name}: {rhe}")
            state.cognitive.error_details = ge.details
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

        except Exception as e:
            logger.error(f"Unexpected error in node {node_name}: {str(e)}")
            state.cognitive.error_details = str(e)
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

    return _safe

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