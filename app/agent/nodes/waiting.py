from langgraph.types import Command
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def _wait_instructions(state: AgentState) -> str:
    """Generate confirmation message for the pending tool."""
    pending_tool = state.cognitive.selected_tool

    if pending_tool == "create_problem":
        formatted = state.cognitive.problem_info_extracted.format_fields()
        return f"Do you want to proceed with the following problem?\n- {formatted}"

    if pending_tool == "create_proposal":
        formatted = state.cognitive.proposal_info_extracted.format_fields()
        return f"Do you want to proceed with the following proposal?\n- {formatted}"

    if pending_tool == "create_scenario":
        items = "\n- ".join(
            x.format_fields() for x in state.cognitive.scenarios_to_generate
        )
        return f"Do you want to proceed with the following scenarios?\n- {items}"

    return "Please confirm to proceed."


def _is_confirmation(user_input: str) -> bool:
    """Check if the user input is a confirmatory reply."""
    confirmatory = {
        "ok", "yes", "sure", "proceed", "go ahead", "confirm", "correct",
        "fine", "agreed", "sounds good", "sì", "va bene", "procedi",
        "confermo", "esatto", "ja", "gut", "weiter", "oui", "d'accord",
        "да", "si",
    }
    return user_input.strip().lower() in confirmatory


def _is_cancellation(user_input: str) -> bool:
    """Check if the user input is a cancellation."""
    cancellation = {
        "no", "cancel", "stop", "abort", "nevermind", "never mind",
        "no grazie", "annulla", "nein", "non",
    }
    return user_input.strip().lower() in cancellation


def wait_user_input_node(state: AgentState):
    """
    Wait node for tool confirmation.

    - If no user_input yet: set confirmation prompt in messages_to_include and route
      to generate_output_message. The API layer detects waiting_for is set and persists
      state; the next request will re-enter with user_input populated.
    - If user confirms: route to tool_executor to run the pending create_* tool.
    - If user cancels: clear pending tool and route to generate_output_message.
    - Otherwise: route back to initialize_tools to re-interpret the new input.

    NOTE: build_output_message is intentionally NOT called here. generate_output_message_node
    is the single place that adds assistant messages, avoiding double conversation updates.
    """
    logger.info(f"Entered WAIT_USER_INPUT node. Pending tool: {state.cognitive.selected_tool}")

    if not state.user_input:
        # First pass: populate messages_to_include with the confirmation prompt and
        # route to generate_output_message to emit it. The graph will then END;
        # waiting_for stays set on the persisted state so the next invocation
        # re-enters here with user_input populated.
        instructions = _wait_instructions(state)
        state.cognitive.messages_to_include = [instructions]

        state.add_trace(
            "human_wait",
            node="WAIT_USER_INPUT",
            data={"pending_tool": state.cognitive.selected_tool},
        )
        return Command(update=state, goto="generate_output_message")

    # Second pass: user has replied
    user_input = state.user_input.strip()
    logger.info(f"User replied while waiting: '{user_input}'")

    if _is_cancellation(user_input):
        logger.info("User cancelled — clearing pending tool")
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.tool_confirmation_needed = False
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto="generate_output_message")

    if _is_confirmation(user_input):
        logger.info("User confirmed — proceeding to tool_executor")
        state.cognitive.tool_confirmation_needed = False
        state.waiting_for = None
        state.user_input = None
        return Command(update=state, goto="tool_executor")

    # Ambiguous or new intent — let tool_selector re-interpret
    logger.info("Ambiguous reply — routing back to tool_selector")
    state.cognitive.tool_confirmation_needed = False
    state.cognitive.selected_tool = None
    state.cognitive.tool_arguments = {}
    state.waiting_for = None
    return Command(update=state, goto="initialize_tools")
