import logging
from langgraph.types import Command
from langgraph.graph import END

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException
from app.utils.common import GraphError
from app.utils.common import truncate_for_prompt, render_agent_message
from app.utils.entity_lists import ENTITY_TYPES
from app.prompts.answer_generation import generate_answer
from app.utils.territory import analyze_page_links, territory_conflict_note

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
        sources = _current_turn_web_search_sources(state)
        if sources:
            output_message = f"{output_message}\n\nSources:\n" + "\n".join(
                f"- [{source.get('title') or source['url']}]({source['url']})"
                for source in sources
            )
    except Exception as e:
        logger.error(f"Error {e}")
        output_message = "System error"
    # Always recomputed (None when the answer has no page link) so a flag from
    # a previous turn can never leak into this one. If the page links cannot
    # be tied to a single territory, no territory is signalled and the answer
    # tells the user to select it manually first.
    signal_territory, territory_conflict = analyze_page_links(state, output_message)
    if territory_conflict:
        output_message = f"{output_message}\n\n{territory_conflict_note(state)}"
    state.signal_territory = signal_territory
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


def _current_turn_web_search_sources(state: AgentState) -> list[dict[str, str]]:
    sources_by_url = {}
    for result_key in state.cognitive.current_turn_result_keys():
        if result_key.split("__", 1)[0] != "web_search":
            continue
        result = state.cognitive.tool_results.get(result_key, {})
        if not result.get("success"):
            continue
        output = result.get("output") or {}
        for source in output.get("sources", []):
            url = source.get("url")
            if url:
                sources_by_url.setdefault(
                    url, {"url": url, "title": source.get("title") or url}
                )
    return list(sources_by_url.values())


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

        case "get_system_capabilities":
            return [output.get("system_description", "System description unavailable.")]

        case "explain_workflow":
            return [output.get("workflow_document", "Workflow document unavailable.")]

        case (
            "list_available_entities"
            | "list_available_problems"
            | "list_available_proposals"
            | "list_available_scenarios"
        ):
            # Preserve the older single-entity wording for persisted state and
            # legacy tool names, while still accepting the merged shape from
            # list_available_entities.
            payload = output.get("items", output)
            if isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in payload.items()
                    if key in ENTITY_TYPES or isinstance(value, list)
                } or payload
            lines = [
                "Here are the available items: "
                f"{truncate_for_prompt(payload, max_chars=8000)}"
            ]
            if output.get("unavailable"):
                lines.append(
                    "The following lists could not be retrieved (say so rather "
                    f"than presenting the answer as complete): {output['unavailable']}"
                )
            return lines

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
            # chart was shown — but only when the widget really was built:
            # an empty/failed result must never be narrated as shown.
            if not output or output.get("success") is False:
                return [
                    output.get(
                        "response",
                        "The requested chart could NOT be shown (no data was "
                        "available for it). Do not say that a chart was displayed.",
                    )
                ]
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
            if output.get("already_pending"):
                return [
                    "The temporary scenario was NOT created: only one temporary "
                    "scenario can exist at a time and another one is still "
                    "waiting to be saved (parameter changes: "
                    f"{truncate_for_prompt(output.get('pending_changes'), max_chars=2000)}). "
                    "Do not say the new values were evaluated. Tell the user, and "
                    "ask whether to save the existing one first or to discard it "
                    "and evaluate the new values instead."
                ]
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
            name = output.get("name") or (tool_result.get("arguments") or {}).get(
                "name"
            )
            return [
                output.get("message")
                or (
                    f"The scenario '{name}' was saved successfully, together with "
                    "its summary."
                    if name
                    else "The scenario was saved successfully, together with its summary."
                )
            ]

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

        case "web_search":
            answer = output.get("answer", "")
            sources = output.get("sources", [])
            source_lines = [
                f"- {source.get('title') or source['url']}: {source['url']}"
                for source in sources
                if source.get("url")
            ]
            if source_lines:
                return [
                    f"Web search findings: {answer}\nSources:\n"
                    + "\n".join(source_lines)
                ]
            return [
                f"Web search findings: {answer}\n"
                "No source URLs were returned; do not present this as verified."
            ]

        case _:
            # Never str(output) here: that dumps Python reprs of the full
            # payload (widget data included) into the prompt. Render it
            # stripped of UI-only fields and length-capped instead.
            return [render_agent_message(output)]
