import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException
from app.utils.common import GraphError
from app.utils.common import truncate_for_prompt
from app.config import GENERAL_ERROR_MESSAGE
from app.prompts.answer_generation import generate_answer

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
        # Full detail (may include internal exception text, backend URLs,
        # etc.) stays in the logs for debugging — it must never be the
        # thing shown to the user.
        logger.error(state.cognitive.error_details)

        with open("logs/errors.txt", "a+") as f:
            f.write(f"{state.cognitive.error_details}\n")

    state.cognitive.messages_to_include = [GENERAL_ERROR_MESSAGE]

    return Command(update=state, goto="generate_output_message")


# ---------------------------------------------------------------------------
# OUTPUT GENERATION
# ---------------------------------------------------------------------------


# Tools whose result is purely an internal resolution step (e.g. id lookups
# used to fill in arguments for later tools this turn) and therefore
# should never be surfaced to the user as part of the final answer.
_INTERNAL_ONLY_TOOLS = {"get_context_ids"}


def generate_output_message_node(state: AgentState) -> Command:
    logger.info("Entering output generation")

    # If tool actions ran this turn and no messages have been prepared yet (e.g. by a
    # clarification/confirmation/error path), build them from EVERY observation produced
    # by this turn's ReAct scratchpad — not just the last one — so that e.g. a
    # "list problems and proposals" request surfaces both lists.
    current_turn_result_keys = state.cognitive.current_turn_result_keys()
    if current_turn_result_keys and not state.cognitive.messages_to_include:
        messages: list[str] = []
        for result_key in current_turn_result_keys:
            tool_result = state.cognitive.tool_results.get(result_key)
            if tool_result is None:
                continue
            # Strip a "__N" collision suffix to get back the real tool name.
            base_tool_name = result_key.split("__", 1)[0]
            if base_tool_name in _INTERNAL_ONLY_TOOLS:
                continue
            messages.extend(
                _build_messages_from_tool_result(base_tool_name, tool_result)
            )
        state.cognitive.messages_to_include = messages

    try:
        output_message = generate_answer(state)
    except Exception as e:
        logger.error(f"Error {e}")
        output_message = "System error"
    state.add_assistant_message(output_message)

    logger.info(f"Output message: {output_message}")

    # Only publish a "final" event / reset the scratchpad when the turn
    # actually concluded. If we're pausing for a confirmation (waiting_for
    # is set), the ReAct loop will resume in this same turn once the user
    # replies — clearing the scratchpad here would wipe out everything
    # reasoned/observed so far and break continuity.
    if not state.waiting_for:
        state.cognitive.scratchpad = []
        state.cognitive.tool_result = None

    state.cognitive.messages_to_include = []

    return Command(update=state, goto=END)


def _build_messages_from_tool_result(tool_name: str, tool_result: dict) -> list[str]:
    """Translate a tool result into messages for the output generator."""

    if not tool_result.get("success", True):
        error = tool_result.get("error", "An unknown error occurred.")
        return [f"The operation failed: {error}"]

    # Unwrap the inner output dict. Guard against "output" being explicitly
    # None (e.g. a backend DELETE call returning an empty/"null" body) so we
    # never crash on output[...] below.
    output = tool_result.get("output", tool_result)
    if output is None:
        output = {}

    match tool_name:

        # TODO: check if I need to insert also other tools. Some don't actually have output are meant to be in-betweens

        case "get_system_capabilities":
            return [output.get("system_description", "System description unavailable.")]

        case (
            "list_available_problems"
            | "list_available_proposals"
            | "list_available_scenarios"
        ):
            # Raw backend payloads grow with tenant data (no bound), so this
            # is hard-capped rather than embedded in full — see
            # app.utils.common.truncate_for_prompt. If the answer needs more
            # than what's shown, the model should say so instead of a call
            # here silently blowing the prompt budget.
            return [f"Here are the available items: {truncate_for_prompt(output, max_chars=4000)}"]

        case "get_context_details":
            return [f"Here are the requested details: {truncate_for_prompt(output, max_chars=4000)}"]

        case "interact_with_context":
            return [output.get("message", "No answer could be generated.")]

        case "create_new_problem" | "create_new_proposal":
            return [f"'{output.get('name', 'The item')}' was created successfully."]

        case "create_new_scenario" | "edit_scenario":
            # TODO
            return [output.get("message", "This feature is not yet implemented.")]

        case "edit_problem" | "edit_proposal":
            return [f"'{output.get('name', 'The item')}' was modified successfully."]

        case "delete_problem" | "delete_proposal" | "delete_scenario":
            return [f"'{output.get('name', 'The item')}' was deleted successfully."]

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
