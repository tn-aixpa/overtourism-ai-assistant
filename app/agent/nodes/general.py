import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException
from app.utils.common import GraphError
from app.utils.common import truncate_for_prompt, render_agent_message
from app.utils.entity_lists import ENTITY_TYPES
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

    # This is an English "seed" for generate_answer, not user-facing text —
    # it goes through the normal messages_to_include -> generate_answer path
    # below, so it's translated into state.user_lang and reshaped by the
    # tone instructions there (propositive, brief, no alarmism) exactly like
    # any other agent message. No hardcoded/pre-translated string needed:
    # this whole node only runs while the LLM is still reachable — if the
    # LLM itself were the thing that failed, we'd never make it to
    # generate_output_message. (The truly LLM-unreachable case is handled
    # separately in api/routes.py's outer exception handler.)
    state.cognitive.messages_to_include = [
        "A technical error occurred and the request could not be completed."
    ]

    return Command(update=state, goto="generate_output_message")


# ---------------------------------------------------------------------------
# OUTPUT GENERATION
# ---------------------------------------------------------------------------


# Tools whose result is purely an internal resolution step (e.g. id lookups
# used to fill in arguments for later tools this turn) and therefore
# should never be surfaced to the user as part of the final answer.
_INTERNAL_ONLY_TOOLS = {"get_context_ids", "get_base_scenario"}


def generate_output_message_node(state: AgentState) -> Command:
    logger.info("Entering output generation")

    # Append messages built from EVERY observation produced by this turn's
    # ReAct scratchpad — not just the last one — so that e.g. a "list
    # problems and proposals" request surfaces both lists.
    #
    # This used to be gated on "and not state.cognitive.messages_to_include",
    # i.e. it only ran when nothing had set a message yet (an error/
    # clarification/confirmation path, or the max-react-steps safety valve
    # — see react_reasoner_node). But a normal "finish" from
    # react_reasoner_node ALSO always sets messages_to_include (to its own
    # short wrap-up line, written from a condensed/truncated view of the
    # observations), which meant this richer, untruncated synthesis never
    # ran on the common path and the wrap-up line silently became the ONLY
    # grounding data generate_answer ever saw for that turn — e.g.
    # analyze_scenario_results' full analysis text was dropped in favor of
    # a one-line gloss like "the comparison chart is shown, details are in
    # the result". This surfaced concretely with show_analysis_widget:
    # calling it alongside analyze_scenario_results in the same turn (as
    # the scenario_analysis guideline requires) needs BOTH the widget
    # confirmation and the actual analysis text to reach the user — losing
    # the latter defeated the pairing. Building these unconditionally and
    # appending them (instead of replacing the wrap-up line) keeps that
    # lead-in while restoring the actual data behind it.
    current_turn_result_keys = state.cognitive.current_turn_result_keys()
    if current_turn_result_keys:
        messages: list[str] = list(state.cognitive.messages_to_include)
        turn_tools = [k.split("__", 1)[0] for k in current_turn_result_keys]
        # get_territorial_index_list is only a lookup step when the turn also
        # ran another tool (plot/map/query): narrating it again just dumps
        # the full index list after every chart. It is shown only when it is
        # the actual answer, i.e. the user asked for the list.
        list_is_lookup_only = "get_territorial_index_list" in turn_tools and any(
            t not in _INTERNAL_ONLY_TOOLS and t != "get_territorial_index_list"
            for t in turn_tools
        )
        for result_key in current_turn_result_keys:
            tool_result = state.cognitive.tool_results.get(result_key)
            if tool_result is None:
                continue
            # Strip a "__N" collision suffix to get back the real tool name.
            base_tool_name = result_key.split("__", 1)[0]
            if base_tool_name in _INTERNAL_ONLY_TOOLS:
                continue
            if base_tool_name == "get_territorial_index_list" and list_is_lookup_only:
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

        case "explain_workflow":
            return [output.get("workflow_document", "Workflow document unavailable.")]

        case "list_available_entities":
            # Raw backend payloads grow with territory data (no bound), so each
            # list is hard-capped rather than embedded in full — see
            # app.utils.common.truncate_for_prompt. Capped per entity type (not
            # on the combined dict) so asking for several kinds at once doesn't
            # shrink each one's share. If the answer needs more than what's
            # shown, the model should say so instead of a call here silently
            # blowing the prompt budget.
            lines = []
            for entity_type in ENTITY_TYPES:
                if entity_type in output:
                    lines.append(
                        f"Available {entity_type}: "
                        f"{truncate_for_prompt(output[entity_type], max_chars=4000)}"
                    )
            if output.get("unavailable"):
                lines.append(
                    "The following lists could not be retrieved (say so rather "
                    f"than presenting the answer as complete): {output['unavailable']}"
                )
            return lines or ["No items were returned."]

        case "get_context_details":
            return [
                f"Here are the requested details: {truncate_for_prompt(output, max_chars=4000)}"
            ]

        case "analyze_scenario_results":
            return [output.get("message", "No answer could be generated.")]

        case "explain_widget":
            return [output.get("message", "No explanation could be generated.")]

        case "show_analysis_widget":
            # The widget's own payload is the raw evaluation dataset behind
            # the chart (see execute_analysis_widget) — large, numeric, and
            # meant for the frontend chart, not for the LLM to narrate. The
            # actual analysis text belongs to analyze_scenario_results,
            # called alongside this tool per the scenario_analysis
            # guidelines. Falling through to the generic `case _` here
            # would dump that whole raw payload into the prompt as an
            # "Agent Message", which is unhelpful and just re-invites the
            # exact bug this function exists to avoid. Just confirm the
            # chart was shown.
            return [output.get("response", "The requested chart was shown.")]

        case "get_territorial_index_list":
            return [
                "Here are the available territorial indexes and additional "
                "indicators that can be combined with a selected index: "
                f"{truncate_for_prompt(output.get('indexes', output), max_chars=8000)}"
                + (
                    " Additional labels (use in combination with one of the indexes): "
                    f"{truncate_for_prompt(output['additional_labels'], max_chars=2500)}"
                    if output.get("additional_labels")
                    else ""
                )
            ]

        case "show_territorial_index_map":
            # The widget itself (geojson) goes to the frontend through
            # assistant_action_data and is never part of this result; only
            # the grounded summary is narrated.
            lines = [output.get("response", "The requested map was shown.")]
            summary = output.get("map_summary")
            if summary:
                lines.append(
                    "Map summary (top/bottom areas by index value): "
                    f"{truncate_for_prompt(summary, max_chars=2000)}"
                )
            return lines

        case "show_territorial_index_plot":
            lines = [output.get("response", "The requested chart was shown.")]
            summary = output.get("plot_summary")
            if summary:
                lines.append(
                    f"Chart parameters: {truncate_for_prompt(summary, max_chars=1000)}"
                )
            series_summary = output.get("series_summary")
            if series_summary:
                lines.append(
                    "Series summary (computed from the plotted data; describe "
                    "how values are distributed, constant series, peaks and "
                    "how the series differ, using ONLY these figures): "
                    f"{truncate_for_prompt(series_summary, max_chars=3500)}"
                )
            return lines

        case "query_territorial_index_values":
            if not output.get("success", True):
                return [output.get("response", "No data was returned for this query.")]
            # Compact, already-filtered figures computed in Python: render them
            # verbatim so the answer can only cite what the backend returned.
            return [
                "Territorial index query result (use ONLY these figures): "
                f"{truncate_for_prompt(output, max_chars=9000)}"
            ]

        case "get_configuration_parameters":
            # Bounded, fixed-size payload (not territory data), so give it a
            # much larger budget than the generic default — see
            # app.utils.common._LARGE_BUDGET_TOOLS.
            return [
                "Here are the tunable simulation parameters, grouped by "
                "category (kind = scalar: a number; categorical: one of the "
                "listed choices or no filter; distribution: a [low, high] "
                f"range): {truncate_for_prompt(output, max_chars=12000)}"
            ]

        case "create_new_temp_scenario":
            if output.get("created") is False:
                lines = [
                    "The temporary scenario was NOT created and nothing was "
                    "evaluated, because the requested values could not be applied. "
                    "Do not say it was evaluated. Explain what is wrong and ask the "
                    "user how to proceed, quoting the allowed values: "
                    f"{truncate_for_prompt(output.get('problems') or output.get('message'), max_chars=3000)}"
                ]
                return lines
            evaluation = output.get("evaluation", {})
            lines = [
                "This is a TEMPORARY, unsaved scenario preview — if it isn't "
                "saved it may be lost. Evaluation results (sustainability "
                f"index and per-constraint breakdown): "
                f"{truncate_for_prompt(evaluation, max_chars=4000)}"
            ]
            changes = output.get("applied_changes") or []
            if changes:
                lines.append(
                    "Parameter changes applied to the base scenario (state them "
                    "to the user; if a change has a note, e.g. a value rounded "
                    "to the allowed step or a single number read as the centre "
                    f"of a range, mention it): "
                    f"{truncate_for_prompt(changes, max_chars=3000)}"
                )
            return lines

        case "create_new_problem":
            return [
                f"The problem '{output.get('name', 'The item')}' was created successfully."
            ]

        case "create_new_proposal":
            return [
                f"The proposal '{output.get('name', 'The item')}' was created successfully."
            ]

        case "create_new_scenario":
            # TODO
            return [output.get("message", "This feature is not yet implemented.")]

        case "edit_problem":
            return [
                f"The problem '{output.get('name', 'The item')}' was modified successfully."
            ]

        case "edit_proposal":
            return [
                f"The proposal '{output.get('name', 'The item')}' was modified successfully."
            ]

        case "edit_scenario":
            return [
                f"The scenario '{output.get('name', 'The item')}' was modified successfully."
            ]

        case "delete_problem":
            return [
                f"The problem '{output.get('name', 'The item')}' was deleted successfully."
            ]

        case "delete_proposal":
            return [
                f"The proposal '{output.get('name', 'The item')}' was deleted successfully."
            ]

        case "delete_scenario":
            return [
                f"The scenario '{output.get('name', 'The item')}' was deleted successfully."
            ]

        case "lookup_glossary":
            matches = output.get("matches", [])
            if not matches:
                return [output.get("message", "No glossary entries found.")]
            lines = []
            for entry in matches:
                lines.append(f"**{entry['term'].capitalize()}**: {entry['definition']}")
                if entry.get("it"):
                    lines.append(f"  Italian term: {entry['it'][0]}")
                if entry.get("aliases"):
                    lines.append(f"  Also known as: {', '.join(entry['aliases'])}")
                if entry.get("related_terms"):
                    lines.append(f"  Related: {', '.join(entry['related_terms'])}")
                if entry.get("examples"):
                    lines.append(f"  Examples: {'; '.join(entry['examples'])}")
            return ["\n".join(lines)]

        case _:
            # Never str(output) here: that dumps Python reprs of the full
            # payload (widget data included) into the prompt. Render it
            # stripped of UI-only fields and length-capped instead.
            return [render_agent_message(output)]
