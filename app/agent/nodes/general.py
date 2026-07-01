import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException
from app.utils.common import GraphError
from app.utils.llm_text_generation import generate_answer


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

        except (RequestHandlingException, GraphError, Exception) as e:
            # Custom behaviour: no errors.txt logging, just surface to user
            logger.warning(f"Request handling error in node {node_name}: {e}")
            state.cognitive.error_details = f"Error in {node_name}: {e}"
            return Command(update=state, goto="error", graph=Command.PARENT)

    return _safe

# ---------------------------------------------------------------------------
# ERROR RECOVERY
# ---------------------------------------------------------------------------

def error_recovery_node(state: AgentState) -> Command:
    logger.info("Entering error recovery node")

    if state.cognitive.error_details:
        logger.error(state.cognitive.error_details)
        
        with open("logs/errors.txt", "a+") as f:
            f.write(f"{state.cognitive.error_details}\n")

    state.cognitive.messages_to_include = [state.cognitive.error_details] if state.cognitive.error_details else ["Something went wrong, please try again later."]

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

    try:
        output_message = generate_answer(state)
    except Exception as e:
        logger.error(f"Error {e}")
        output_message = "System error"
    state.add_assistant_message(
        output_message
    )

    logger.info(f"Output message: {output_message}")

    state.cognitive.messages_to_include = []
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

        #TODO: check if I need to insert also other tools. Some don't actually have output are meant to be in-betweens

        case "get_system_capabilities":
            return [output.get("system_description", "System description unavailable.")]

        case "list_available_problems" | "list_available_proposals" | "list_available_scenarios" :
            return [f"Here are the available items: {output}"]

        case "get_context_details":
            return [f"Here are the requested details: {output}"]

        case "interact_with_context":
            return [output.get("message", "No answer could be generated.")]
        
        case "create_new_problem" | "create_new_proposal":
            return [
                f"'{output['name']}' was created successfully."
            ]

        case "create_new_scenario":
            return [output.get("message", "This feature is not yet implemented.")]

        case "lookup_glossary":
            matches = output.get("matches", [])
            if not matches:
                return [output.get("message", "No glossary entries found.")]
            lines = []
            for entry in matches:
                lines.append(f"**{entry['term'].capitalize()}**: {entry['definition']}")
                if entry.get("aliases"):
                    lines.append(f"  Also known as: {', '.join(entry['aliases'])}")
                if entry.get("related_terms"):
                    lines.append(f"  Related: {', '.join(entry['related_terms'])}")
                if entry.get("examples"):
                    lines.append(f"  Examples: {'; '.join(entry['examples'])}")
            return ["\n".join(lines)]

        case _:
            return [str(output)]