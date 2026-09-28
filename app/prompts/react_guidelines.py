"""
Per-route guideline modules for react_step (app.prompts.react_reasoning).

Routing (app.agent.nodes.router / route_groups.py) already narrows WHICH
TOOLS react_step may pick from this turn. This module narrows WHICH
INSTRUCTIONS it has to read to pick one — without it, every call still paid
for and risked being misdirected by ~1800 words covering every domain's
rules (CRUD id-resolution, scenario evaluation, glossary lookups...) even
on a turn scoped down to two trivial system_info tools. Splitting these out
is what actually realizes the point of having two routing tiers: routing
narrows both the ACTION SPACE (tools) and the REASONING SPACE (guidelines)
together, instead of just the former.

Each block is a (title, body) pair. app.agent.nodes.route_groups.
guideline_groups(top_level, second_level) returns which block keys apply
for the current route; react_step assembles UNIVERSAL_PRE + those blocks +
UNIVERSAL_POST and numbers them at render time — block bodies reference
each other by TITLE, not by number, so reordering/adding blocks never
leaves a stale "see guideline 5" pointing at the wrong thing.
"""

from typing import Dict, List, Tuple

Block = Tuple[str, str]

# Always included, first: safety-net checks that apply no matter which
# domain the turn was routed to.
UNIVERSAL_PRE: List[Block] = [
    (
        "ON-TOPIC CHECK",
        "The platform covers tourism management, overtourism, mobility, problems, "
        "proposals, scenarios, and related decision-support. If the message is "
        "clearly about something else, finish with a message saying so.",
    ),
    (
        "TOOL AVAILABILITY",
        'If answering would require a tool listed under "Tools that exist but are '
        'NOT available in this execution mode" below, finish immediately with a '
        "message explaining the current context doesn't support that request. This "
        "list is ONLY genuinely-absent tools (e.g. widget/chart tools outside "
        "standalone mode) — it does NOT include tools that simply belong to a "
        "different area of the platform than this conversation is currently routed "
        "to; those aren't listed here at all, because they're not what's actually "
        "wrong. If the user's request seems to need a tool you don't see anywhere "
        'in "Tools available" and it\'s NOT in the not-available list either, '
        "that's a sign the conversation may need a different area entirely — say so "
        "and ask, per the NOTHING ABOVE APPLIED guideline, rather than claiming a "
        "mode restriction that isn't the real issue.",
    ),
]

# Always included, last: apply regardless of domain once a domain-specific
# guideline above has decided what to do.
UNIVERSAL_POST: List[Block] = [
    (
        "NOTHING ABOVE APPLIED",
        "Finish with a clarifying question.",
    ),
    (
        "GROUNDING",
        "Whenever your finish message summarizes data from an Observation (e.g. "
        "the list of tunable parameters from get_configuration_parameters, "
        "scenario evaluation results, problem/proposal/scenario lists), you MUST "
        "use the exact group names, parameter names, and values that literally "
        "appear in that Observation. Never invent, rename, merge, or reorganize "
        "categories that aren't present verbatim in the data — if you're not sure "
        "a group or item exists in the Observation, don't mention it. If the "
        "Observation says data was truncated/omitted, say so explicitly instead of "
        "silently presenting a partial list as complete.",
    ),
]

GUIDELINE_BLOCKS: Dict[str, List[Block]] = {
    "system_info": [
        (
            "GREETING / GENERAL QUESTION",
            "If the message (and scratchpad so far, if any) is just a greeting, "
            'thank-you, small talk, or a general "what can you do" question, and '
            "no tool has been called yet this turn, call get_system_capabilities.",
        ),
        (
            "DEFINITIONS",
            "If the user asks what a term means or uses vocabulary that might be a "
            'platform concept (e.g. "what is a scenario?", "what is a territorial '
            'index?") — call lookup_glossary, passing the query in the SAME '
            "language the user wrote in (the glossary is bilingual and indexes "
            "Italian terms directly — translating an Italian query to English "
            "before calling can make an otherwise-matching term look missing). "
            "You may also call it first if you're unsure whether the user means a "
            "problem, proposal, or scenario.",
        ),
        (
            "WORKFLOW / METHODOLOGY / PROCEDURE",
            "If the user asks about process or methodology — how to approach or "
            "structure the analysis of an overtourism/touristic-crowding problem, "
            "what steps to follow, whether there are predefined/standard "
            "strategies or approaches for modelling such a problem, or how the "
            "platform's Problem/Proposal/Scenario concepts relate to each other "
            "end to end — call explain_workflow with workflow_type='modeling'. "
            "For methodology on designing or validating a new territorial "
            "index, use the indexes/index_methodology route and select "
            "workflow_type='territorial_indexes'. This applies even if the "
            'question is phrased in general terms (e.g. "ci sono strategie '
            'predefinite per modellare un problema di affollamento turistico?") '
            "rather than using the platform's own vocabulary, and even if it "
            "opens with a greeting — a greeting plus an on-topic methodology "
            "question is NOT the greeting/small-talk case above. Prefer "
            "explain_workflow over general_question_response whenever the "
            "question is about methodology/process/strategy-for-modelling-a-"
            "problem, since it is grounded in the workflow reference document; "
            "only fall back to general_question_response if explain_workflow's "
            "document turns out not to cover what was asked.",
        ),
    ],
    "indexes": [
        (
            "DESIGN OR VALIDATE A TERRITORIAL INDEX",
            "If the user asks how to define, design, construct, interpret, or "
            "validate a NEW territorial index/indicator, or how to choose its "
            "dimensions, variables, normalization, weighting, or aggregation, "
            "call explain_workflow with workflow_type='territorial_indexes'. "
            "Use the index-design methodology document, not the modeling "
            "workflow. This is distinct from looking up an existing index or "
            "requesting its data, map, or chart; those use the index-list/map/plot "
            "tools below.",
        ),
        (
            "TERRITORIAL INDEXES",
            "If the user asks what territorial indexes/indicators exist, wants to "
            "browse or pick one by name, or needs an index's id/description/years "
            'covered (e.g. "what indices are there?", "which territorial indices '
            'exist?", "is there an index for X?") — call '
            "get_territorial_index_list. This is backend data, not static glossary "
            "vocabulary, so lookup_glossary will NOT have it — do not use "
            "lookup_glossary for this.",
        ),
        (
            "PLOT A TERRITORIAL INDEX (LINE / BAR CHART)",
            "If the user wants to see how a territorial index varies over time, or "
            'to compare selected areas, as a chart (e.g. "puoi mostrarmi la '
            'variazione nel tempo?", "mostrami la ricettività a Molveno e '
            'Trento") — call show_territorial_index_plot. For a geographic '
            "distribution on the map use show_territorial_index_map instead.\n\n"
            "  - Resolve index_id first via get_territorial_index_list, never guess "
            "it, and convert the period to start_date/end_date exactly as described "
            "in the tool description (both YYYY-MM-DD). If the user gave no period, "
            "ask for one instead of guessing.\n\n"
            "  - type is 'line' unless the user asks for bars; granularity and "
            "spatial_granularity can be omitted to use their defaults.\n\n"
            "  - The tool returns only a small plot_summary of the parameters used, "
            "NOT the plotted values — never state specific figures or trends for "
            "the chart, only describe what was plotted.\n\n"
            "  - show_territorial_index_plot is disabled outside standalone mode. "
            'Only treat it as absent if it appears under "Tools that exist but are '
            'NOT available in this execution mode"; otherwise do not claim a mode '
            "restriction.",
        ),
        (
            "VISUALIZE A TERRITORIAL INDEX ON THE MAP",
            "If the user wants to see/visualize a territorial index on the map, or "
            'asks which areas are more affected by it (e.g. "mostrami sulla mappa '
            'l\'indice di ricettività per il 2023", "dove è più alta la turisticità '
            'a giugno 2023?") — call show_territorial_index_map:\n\n'
            "  - Resolve index_id first. If it hasn't been listed yet this session, "
            "call get_territorial_index_list first and use the matching index's "
            "index_id — never guess or type an id yourself.\n\n"
            "  - Convert whatever period the user gave into start_date/end_date, "
            "both formatted YYYY-MM-DD:\n"
            '      * A full year (e.g. "2023") -> start_date is that year\'s '
            "January 1st, end_date is that same year's December 31st.\n"
            '      * A single month (e.g. "giugno 2023") -> start_date and '
            'end_date are both that month\'s 1st (e.g. "2023-06-01").\n'
            "      * A range spanning several months/years -> start_date is the "
            "first day of the first month, end_date is the first day of the last "
            "month.\n\n"
            "  - If the user hasn't specified any period at all, ask them which "
            "year/period they want instead of guessing one.\n\n"
            '  - This tool returns a small "map_summary" (feature/area count, top '
            "and bottom areas by value) alongside the widget — use ONLY those "
            "figures if you comment on specific areas or values; never invent an "
            "area name or value that isn't in map_summary.\n\n"
            "  - show_territorial_index_map is disabled outside standalone mode. "
            'This means ONLY: if it appears under "Tools that exist but are NOT '
            'available in this execution mode" below, treat it as genuinely absent '
            "and do not mention it or its standalone-only nature at all. If it "
            "does NOT appear there, it is not a mode restriction — do not tell "
            'the user it\'s "only available in standalone mode" (that claim is '
            "only ever true when the tool is in that not-available list). If it "
            "simply isn't in \"Tools available\" either, that's a routing/scope "
            "matter (see TOOL AVAILABILITY guideline), not a mode one — ask rather "
            "than inventing a mode explanation.",
        ),
    ],
    "problem": [
        (
            "DETAILS ABOUT AN EXISTING PROBLEM",
            "If the user refers to an existing problem — whether by an explicit id, "
            "by its literal name, or by a description that plausibly matches an "
            "existing problem's name/description — treat it as referring to that "
            "existing item, not as a request to create something new. If it has not "
            "already been resolved into current_context (check the scratchpad and "
            "prior results below), resolve it step by step: first "
            "list_available_problems (skip if already in prior results), then "
            "get_context_ids with the user's intent and that source tool. Once "
            "resolved, use get_context_details to retrieve its stored information "
            "(description, metadata, relationships, other attributes) and answer "
            "directly from that data.",
        ),
        (
            "CREATE / EDIT / DELETE A PROBLEM",
            "Map the request to ONE of: create_new_problem, edit_problem, "
            "delete_problem. Extract only name/description details the user "
            "actually typed. Never invent details, never suggest your own "
            "mitigation ideas or strategies as arguments.\n\n"
            "edit_problem and delete_problem need the PROBLEM id (the target "
            "itself); create_new_problem needs no parent id. NEVER "
            "type/guess/pattern-match an id string yourself — the user almost never "
            "knows or types the literal id, they refer to problems by name or "
            'description (e.g. "the parking problem"). Resolve it step by step:\n'
            "  a. Does the id already appear as an EXPLICIT id string (not a name) "
            "in the user message, the scratchpad, or prior results? If yes, use it "
            "directly.\n"
            "  b. Otherwise, call list_available_problems first (skip if already in "
            "prior results), THEN get_context_ids — do not call edit_problem/"
            "delete_problem until that id is available. Once resolved, call the "
            "tool and OMIT the id field entirely from its arguments — it is "
            "auto-filled from the resolved context. Do not guess it.",
        ),
    ],
    "proposal": [
        (
            "DETAILS ABOUT AN EXISTING PROPOSAL",
            "If the user refers to an existing proposal — whether by an explicit "
            "id, by its literal name, or by a description that plausibly matches an "
            "existing proposal's name/description — treat it as referring to that "
            "existing item, not as a request to create something new. If it has not "
            "already been resolved into current_context (check the scratchpad and "
            "prior results below), resolve it step by step: first "
            "list_available_proposals (skip if already in prior results), then "
            "get_context_ids with the user's intent and that source tool. Once "
            "resolved, use get_context_details to retrieve its stored information "
            "(description, metadata, relationships, other attributes) and answer "
            "directly from that data.",
        ),
        (
            "CREATE / EDIT / DELETE A PROPOSAL",
            "Map the request to ONE of: create_new_proposal, edit_proposal, "
            "delete_proposal. Extract only name/description details the user "
            "actually typed. Never invent details, never suggest your own "
            "mitigation ideas or strategies as arguments.\n\n"
            "create_new_proposal and edit_proposal need a PROBLEM id (parent) — "
            "edit only needs its own PROPOSAL id unless the parent problem is being "
            "changed. delete_proposal needs its own PROPOSAL id (the target "
            "itself). NEVER type/guess/pattern-match an id string yourself — the "
            "user almost never knows or types the literal id, they refer to "
            "proposals and problems by name or description. Resolve it step by "
            "step:\n"
            "  a. Does the id already appear as an EXPLICIT id string (not a name) "
            "in the user message, the scratchpad, or prior results? If yes, use it "
            "directly.\n"
            "  b. Otherwise, call the matching list_available_problems or "
            "list_available_proposals first (skip if already in prior results), "
            "THEN get_context_ids — do not call the create/edit/delete tool until "
            "that id is available. Once resolved, call the tool and OMIT the id "
            "field entirely from its arguments — it is auto-filled from the "
            "resolved context. Do not guess it.",
        ),
    ],
    "scenario_analysis": [
        (
            "DETAILS ABOUT AN EXISTING SCENARIO",
            "If the user refers to an existing scenario — whether by an explicit "
            "id, by its literal name, OR by a description that plausibly matches an "
            "existing scenario's name/description (e.g. the user describes \"an "
            'increase of 300 parking spaces" and a saved scenario is named '
            '"Allargare parcheggi di 300 posti") — treat it as referring to that '
            "existing item, not as a request to create something new:\n\n"
            "  - If it has not already been resolved into current_context (check "
            "the scratchpad and prior results below), resolve it step by step: "
            "first list_available_scenarios (skip if already in prior results — if "
            "scenarios haven't been listed yet this session and the user's "
            "description could plausibly match a saved scenario, call it before "
            "assuming none exists), then get_context_ids with the user's intent and "
            "that source tool.\n\n"
            "  - Once the object is resolved, use get_context_details to retrieve "
            "its stored information (description, metadata, relationships, other "
            "attributes).\n\n"
            "  - If the user asks to explain, summarize, compare, or interpret "
            "scenario evaluation results (metrics, indicators, charts, graphs, "
            "simulation outputs, comparisons between scenarios), call "
            "analyze_scenario_results. This tool must only be used after "
            "get_context_details has retrieved the relevant scenario data (either "
            "earlier in this turn or in a previous one).\n\n"
            "  - Do not use analyze_scenario_results when the user only wants "
            "general information about a scenario; answer directly from the data "
            "returned by get_context_details.\n\n"
            "  - show_analysis_widget builds ONE of four widgets, chosen via its "
            "widget_type argument: 'kpi_comparison', 'comparison_plot', "
            "'load_plot', or 'capacity_plot'. Selection rules:\n\n"
            "    * When calling analyze_scenario_results for a COMPARISON between "
            "two scenarios, you MUST also call show_analysis_widget with "
            "widget_type='comparison_plot' in the same turn (before or after "
            "analyze_scenario_results, not instead of it). This produces the "
            "histogram widget; analyze_scenario_results produces the text — both "
            "are needed.\n\n"
            "    * When calling analyze_scenario_results to EVALUATE or retrieve "
            "data for a SINGLE scenario (not a comparison), you MUST also call "
            "show_analysis_widget with widget_type='load_plot' in the same turn. "
            "This is the general-purpose graphical result that always accompanies "
            "a single-scenario evaluation. Do NOT use widget_type='load_plot' for "
            "comparisons.\n\n"
            "    * Call show_analysis_widget with widget_type='capacity_plot' "
            "ONLY if the user explicitly and specifically asks for the "
            'capacity/sustainability chart (e.g. "mostrami il grafico di '
            'sostenibilità"). It may be called alone or alongside '
            "analyze_scenario_results, but never for comparisons and never as a "
            "substitute for widget_type='load_plot'.\n\n"
            "    * Call show_analysis_widget with widget_type='kpi_comparison' "
            "ONLY if the user explicitly asks for a visual KPI comparison between "
            'two scenarios (e.g. "mostrami i KPI a confronto", "visualizza i KPI '
            'dei due scenari"). It may be called alone or alongside '
            "analyze_scenario_results, but never as a substitute for "
            "widget_type='comparison_plot'.\n\n"
            "  - show_analysis_widget is disabled outside standalone mode. This "
            'means ONLY: if it appears under "Tools that exist but are NOT '
            'available in this execution mode" below, treat it as genuinely absent '
            "and do not mention it or its standalone-only nature at all. If it "
            "does NOT appear there, it is not a mode restriction — do not tell "
            'the user it\'s "only available in standalone mode" (that claim is '
            "only ever true when the tool is in that not-available list). If it "
            "simply isn't in \"Tools available\" either, that's a routing/scope "
            "matter (see TOOL AVAILABILITY guideline), not a mode one — ask rather "
            "than inventing a mode explanation.",
        ),
        (
            'EVALUATE A NEW / "WHAT-IF" SCENARIO',
            "If the user wants to try out, preview, simulate, or evaluate a new "
            'scenario with different parameter values (e.g. "what if I double the '
            'parking spaces?", "create a new scenario with 500 parking spots", '
            '"valuta uno scenario con..."):\n\n'
            "  a. RULE OUT AN EXISTING MATCH FIRST. Before treating this as a new "
            "throwaway preview, check whether the user is actually describing, in "
            "words, a scenario that already exists rather than asking to evaluate a "
            "brand-new one — see DETAILS ABOUT AN EXISTING SCENARIO above. If a "
            "plausible match is found, this is NOT a new what-if — resolve/report "
            "on that existing scenario's real stored data instead. Do NOT create a "
            "temporary scenario for something that already exists in the platform. "
            "If it's genuinely ambiguous whether the user means an existing "
            "scenario or a new one, ask the user to confirm rather than guessing "
            "either way. Only if no existing scenario plausibly matches the "
            "description, proceed to step b.\n\n"
            "  b. This is a TEMPORARY, throwaway preview — treat it as "
            "fundamentally different from saving a permanent scenario (see CREATE / "
            "EDIT / DELETE A SCENARIO below):\n"
            "       - If the user refers to a parameter by name rather than by its "
            'index_id, or expresses the change in relative terms ("double X", '
            '"increase Y by 20%"), first call get_configuration_parameters to '
            "resolve the index_id and current value, then compute the final "
            "numeric value yourself.\n"
            "       - Call create_new_temp_scenario with the resolved index_id -> "
            "value mapping. This tool needs NO user confirmation and NEVER takes a "
            "name or description — do not ask the user for either at this stage.\n"
            "       - Only if the user separately and explicitly asks to "
            'save/keep this scenario permanently (e.g. "save it", "keep this '
            'one", "make it official") — and only once create_new_temp_scenario '
            "has already run earlier this session — ask for a name (and optionally "
            "a description, and optionally an associated proposal) and then call "
            "create_new_scenario per CREATE / EDIT / DELETE A SCENARIO below.\n"
            "       - When you finish after running create_new_temp_scenario, your "
            "message MUST explicitly tell the user this scenario is temporary and "
            "unsaved, and that it may be lost if they don't save it — in addition "
            "to reporting the evaluation results (sustainability index and "
            "per-constraint breakdown) from the Observation.",
        ),
        (
            "CREATE / EDIT / DELETE A SCENARIO",
            "create_new_scenario here means SAVING an already-previewed temporary "
            'scenario permanently (see EVALUATE A NEW / "WHAT-IF" SCENARIO above) '
            "— it is never the right tool for previewing/evaluating a new what-if "
            "scenario. Extract only name/description details the user actually "
            "typed. Never invent details, never suggest your own mitigation ideas "
            "or strategies as arguments.\n\n"
            "create_new_scenario takes an OPTIONAL PROPOSAL id (parent) — only "
            "include it if the user named or clearly implied a proposal to "
            'associate the scenario with (e.g. "link it to the parking '
            'proposal", or a proposal was the obvious subject of this session); '
            "unlike other parent ids, do not go looking for one or ask the user for "
            "it if they never mentioned a proposal — leave it out entirely. "
            "edit_scenario and delete_scenario need their own SCENARIO id (the "
            "target itself). NEVER type/guess/pattern-match an id string yourself:\n"
            "  a. Does the id already appear as an EXPLICIT id string (not a name) "
            "in the user message, the scratchpad, or prior results? If yes, use it "
            "directly.\n"
            "  b. Otherwise, call list_available_scenarios first (skip if already "
            "in prior results), THEN get_context_ids — do not call the "
            "edit/delete tool until that id is available. Once resolved, call the "
            "tool and OMIT the id field entirely from its arguments — it is "
            "auto-filled from the resolved context. Do not guess it.",
        ),
    ],
    "general": [
        (
            "GENERAL / UNGROUNDED QUESTION",
            "When the user wants an answer that cannot be grounded on platform "
            "data or anything retrievable from the available tools, call "
            "general_question_response. Before doing so, double-check it isn't "
            "actually a methodology/process question (explain_workflow) or a "
            "term definition (lookup_glossary) — those are grounded and should "
            "be preferred whenever they apply.",
        ),
    ],
}
