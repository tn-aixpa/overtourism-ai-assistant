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

# Shared guideline blocks reused by several routes.
_RELATIONSHIPS_BLOCK: Block = (
    "RELATIONSHIPS BETWEEN PROBLEMS, PROPOSALS AND SCENARIOS",
    "Associations are explicit in the data: a problem's `linked_proposals`, a "
    "proposal's `linked_scenarios` and a scenario's `linked_proposals` (in "
    "list_available_entities and get_context_details results). Answer every "
    "question about which scenarios belong to a proposal, which proposals a "
    "scenario is associated with, or how many there are, ONLY from those "
    "fields — never infer an association from names, from order, or from the "
    "territory-wide list of scenarios (a territory can have more scenarios "
    "than a proposal). The BASE scenario (is_base_scenario=true) is associated "
    "by default with EVERY proposal: always count and list it among a "
    "proposal's scenarios, saying it is the reference (as-is) scenario, and "
    "never say it is 'not associated' or that a proposal has 'no scenarios' "
    "when linked_scenarios contains it. Only say that an association is "
    "unknown if the relevant linked_* field is absent from the data, and then "
    "say you could not retrieve it rather than that it does not exist.",
)

_TERMINOLOGY_BLOCK: Block = (
    "PROBLEM = AMBITO DI ANALISI",
    "In Italian, 'ambito di analisi' and 'problema' are TWO NAMES FOR THE SAME "
    "ENTITY: the Problem (it holds the critical situation, its territory, "
    "name, description and objective; period and phenomena studied belong in "
    "its description/objective). There is no separate 'ambito di analisi' "
    "object. So: a request to create, edit, delete or describe an 'ambito di "
    "analisi' is a request on a PROBLEM and uses the problem tools; a "
    "proposal is linked to the problem (= the ambito di analisi) and never to "
    "a separate ambito. Never say an ambito di analisi 'can only be kept as "
    "conversation context', 'cannot be registered as an autonomous element' "
    "or 'is different from the problem'. If the user lists several things "
    "to create (e.g. an ambito di analisi AND a proposal), that is a problem "
    "and a proposal: follow the ONE AT A TIME rule, starting with the "
    "problem.",
)

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
        'NOT available in this execution mode" below, do not attempt that action. '
        "Explain the user-facing limitation briefly and offer a useful alternative; "
        "never mention tools, execution modes, or that the current context has no "
        "operative tools. This "
        "list is ONLY genuinely-absent tools (e.g. widget/chart tools outside "
        "standalone mode) — it does NOT include tools that simply belong to a "
        "different area of the platform than this conversation is currently routed "
        "to; those aren't listed here at all, because they're not what's actually "
        "wrong. If the user's request seems to need a tool you don't see anywhere "
        'in "Tools available" and it\'s NOT in the not-available list either, '
        "that's a sign the conversation may need a different area entirely — ask "
        "what information the user needs rather than describing internal routing "
        "or tool availability.",
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
    (
        "NEVER CLAIM A FEATURE IS 'NOT IMPLEMENTED'",
        "Never tell the user that a function, feature or comparison 'is not yet "
        "implemented', 'does not exist' or 'is not available', and never say that "
        "a scenario's values 'are not available here' unless a tool actually "
        "returned that. Comparing two scenarios IS supported: when the user asks "
        "for a comparison (including 'questo scenario' = the scenario just created "
        "or previewed, compared with the base scenario or another one), obtain "
        "both scenario ids (get_base_scenario for the base scenario; the id "
        "returned by create_new_temp_scenario / the saved scenario for the new "
        "one; otherwise list_available_entities + get_context_ids), then call "
        "analyze_scenario_results and show_analysis_widget with "
        "widget_type='comparison_plot' as described in the scenario guidelines. "
        "If data for a scenario is missing, retrieve it with the tools before "
        "answering. If something genuinely cannot be done (for example a "
        "temporary scenario that is no longer pending because only the most "
        "recent one can be saved), say plainly what is possible instead and "
        "offer to redo it (e.g. recreate that scenario) — in user-facing terms, "
        "without blaming the platform.",
    ),
    (
        "WHEN THE USER WANTS TO STOP OR IS FRUSTRATED",
        "If the user says they want to drop the topic, gives up, or expresses "
        "frustration (e.g. 'lasciamo perdere', 'sei andato in tilt'), the user "
        "alone decides whether the conversation continues. Reply with one short, "
        "professional line of apology and an open offer of help — for example "
        "'Mi dispiace per l'inconveniente. Resto a disposizione se hai bisogno di "
        "altro.' — optionally followed by ONE concrete thing you can do next. "
        "NEVER write phrases that close the conversation on the user's behalf, such "
        "as 'Interrompiamo qui', 'Chiudiamo qui', 'Fermiamoci qui', 'Basta così'; "
        "never list what went wrong at length and never ask them to start over.",
    ),
    (
        "CONTEXT (TERRITORY) SWITCHES",
        "The territory shown in the context line above may have been changed to "
        "the one the user asked for at the START of this very turn. When the "
        "context line says the territory was switched this turn, the request to "
        "change context HAS JUST BEEN CARRIED OUT: confirm the change and name "
        "both territories, e.g. 'Ho cambiato contesto: ora lavoriamo su Fazzon "
        "(prima eravamo su Molveno).' NEVER say the context 'is already' the "
        "requested one, or that the switch 'had already happened'. If the user "
        "later clarifies what they were working on before, agree using the "
        "recorded previous territory, in the order they happened (first Molveno, "
        "now Fazzon), without apologising for 'reconstructing the sequence'.",
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
            "document turns out not to cover what was asked.\n\n"
            "When describing how the concepts are organised, use exactly this "
            "structure: Problema (also called 'ambito di analisi' — the same "
            "entity, not two steps) -> Proposta -> Scenario. A Scenario IS the "
            "simulation: it is created and evaluated with the digital twin, so "
            "'simulazione' is not a separate stage after it. Comparing scenarios "
            "is an optional analysis the user can run on scenarios, not a stage "
            "of the chain. Never present 'Ambito di analisi' or 'Simulazione e "
            "confronto' as separate steps.",
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
            "covered (e.g. 'what indices are there?', 'which territorial indices "
            "exist?', 'is there an index for X?') — call "
            "get_territorial_index_list. This is backend data, not static glossary "
            "vocabulary, so lookup_glossary will NOT have it — do not use "
            "lookup_glossary for this.",
        ),
        (
            "NUMERIC QUESTIONS ABOUT A TERRITORIAL INDEX",
            "If the user asks for the VALUE of a territorial index for one or more "
            'named municipalities (e.g. "qual è la ricettività a Molveno e Trento '
            'nel 2023?"), or which municipalities — or how many — have an index '
            'above/below a given value (e.g. "quali comuni hanno turisticità '
            'superiore a 0.5?", "quanti comuni sono sotto 0.2?"), including '
            "questions about what the map shows — call query_territorial_index_values "
            "instead of a map or chart:\n\n"
            "  - Resolve index_id first via get_territorial_index_list, never guess "
            "it, and convert the period to start_date/end_date as described in the "
            "tool description. If the user gave no period, ask for one instead of "
            "guessing.\n\n"
            "  - The list also includes additional_labels that combine with a concrete "
            "index. For 'tasso-variazione', use its id as index_id and pass the chosen "
            "indicator id plus start_date_comparison/end_date_comparison. For "
            "'incidenza-periodo', pass the chosen indicator id and seasonality "
            "('weekend', 'weekdays', 'festivities', 'summer-months', or 'winter-months').\n\n"
            "  - Named municipalities -> query_type='values' with the names as the "
            "user wrote them. Above/below a value -> query_type='threshold' with "
            "threshold and operator ('>' / '<' unless the user says at "
            "least/at most); set count_only=true if only the number is asked. "
            "For 'the N municipalities with the highest/lowest values', use "
            "query_type='ranking', ranking_order='highest'/'lowest', and top_n=N. "
            "If no N is specified, omit top_n (default 5). If the result says "
            "ranking_tie_expanded, report how many municipalities share the extreme "
            "value and list all tied names when returned; if ranking_list_omitted is "
            "true, state the tie count only and do not invent/list municipality names. "
            "For a calendar year Y, set start_date=YYYY-01-01 and end_date=YYYY-12-31.\n\n"
            "  - Report ONLY figures and municipality names present in the tool "
            "result. If 'not_found' is non-empty, say which names weren't matched "
            "(offering 'did_you_mean' suggestions when present); if "
            "'list_truncated' is true, say the list is partial and give "
            "'matching_count' as the exact total. Never compute, estimate or "
            "complete values yourself.\n\n"
            "  - The result gives the real extremes of the data as lowest_value and "
            "highest_value. When asked for the range, the minimum or the maximum, "
            "use ONLY those two fields (and a ranking query to name the area). "
            "Never quote the colour-scale bounds of the map as data extremes: they "
            "are rounded for display and can differ from the actual values.\n\n"
            "  - To merely SEE the distribution, use show_territorial_index_map "
            "instead.",
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
            "  - type is 'line' unless the user asks for bars; granularity can be "
            "omitted to use its default.\n\n"
            "  - The territorial level is inferred from selected_territories: pass "
            "the municipality names OR the macro-area (APT) names the user asked "
            "for, never a mix of the two (if the user mixes them, ask which level "
            "they want). Omit selected_territories only when the user wants the "
            "whole province. Set include_provincia=true when they also want the "
            "overall provincial value alongside the selected municipalities/APTs. "
            "If the tool reports unmatched or ambiguous names, ask the user which "
            "territory they mean.\n\n"
            "  - After the chart is shown, finish with ONE short confirmation of what "
            "was plotted. Do NOT repeat or list the available indexes (the list was "
            "only a lookup step).\n\n"
            "  - The tool returns a plot_summary of the parameters used and a "
            "series_summary computed from the plotted data (min/max/mean, peaks, "
            "constant series, trend, and how series differ). After the chart, "
            "describe the result using ONLY the figures in series_summary; never "
            "invent values, months or trends that are not in it. If "
            "series_summary is absent, only describe what was plotted.\n\n"
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
            "  - Additional labels from that list are used in combination with a "
            "concrete indicator: for 'tasso-variazione', pass its id as index_id, "
            "the concrete indicator id, and both comparison dates; for "
            "'incidenza-periodo', pass its id as index_id, the concrete indicator id, "
            "and the required seasonality ('weekend', 'weekdays', 'festivities', "
            "'summer-months', or 'winter-months').\n\n"
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
            "and bottom areas by value, lowest_value and highest_value) alongside "
            "the widget — use ONLY those figures if you comment on specific areas "
            "or values; never invent an area name or value that isn't in "
            "map_summary. State the range of the data only from lowest_value / "
            "highest_value, never from the colour scale of the map.\n\n"
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
            "LIST PROBLEMS",
            "When the user asks for problems in a territory and the list has been "
            "retrieved, report the problem names naturally as problems defined for "
            "that territory (for one item, e.g. 'Per Fazzon è stato definito questo "
            "problema: …'). Do not say 'Hai indicato il problema disponibile' or "
            "imply that the user selected a problem when they only selected a "
            "territory from a numbered territory menu.",
        ),
        (
            "DETAILS ABOUT AN EXISTING PROBLEM",
            "If the user refers to an existing problem — whether by an explicit id, "
            "by its literal name, or by a description that plausibly matches an "
            "existing problem's name/description — treat it as referring to that "
            "existing item, not as a request to create something new. If it has not "
            "already been resolved into current_context (check the scratchpad and "
            "prior results below), resolve it step by step: first "
            "list_available_entities with entity_types=['problems'] (skip if "
            "problems are already in prior results), then get_context_ids with "
            "the user's intent. Once "
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
            "ONE AT A TIME: create only ONE problem, proposal or scenario per "
            "request. If the user asks for several, handle only the first and "
            "tell them to ask for the next one afterwards.\n\n"
            "edit_problem and delete_problem need the PROBLEM id (the target "
            "itself); create_new_problem needs no parent id. NEVER "
            "type/guess/pattern-match an id string yourself — the user almost never "
            "knows or types the literal id, they refer to problems by name or "
            'description (e.g. "the parking problem"). Resolve it step by step:\n'
            "  a. Does the id already appear as an EXPLICIT id string (not a name) "
            "in the user message, the scratchpad, or prior results? If yes, use it "
            "directly.\n"
            "  b. Otherwise, call list_available_entities with "
            "entity_types=['problems'] first (skip if problems are already in "
            "prior results), THEN get_context_ids — do not call edit_problem/"
            "delete_problem until that id is available. Once resolved, call the "
            "tool and OMIT the id field entirely from its arguments — it is "
            "auto-filled from the resolved context. Do not guess it.",
        ),
        _TERMINOLOGY_BLOCK,
        _RELATIONSHIPS_BLOCK,
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
            "list_available_entities with entity_types=['proposals'] (skip if "
            "proposals are already in prior results), then get_context_ids with "
            "the user's intent. Once "
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
            "ONE AT A TIME: create only ONE problem, proposal or scenario per "
            "request. If the user asks for several, handle only the first and "
            "tell them to ask for the next one afterwards.\n\n"
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
            "  b. Otherwise, call list_available_entities first with the "
            "entity_types you need — ['problems'] for a parent problem, "
            "['proposals'] for the proposal itself, or both in the same call "
            "(skip lists already in prior results), "
            "THEN get_context_ids — do not call the create/edit/delete tool until "
            "that id is available. Once resolved, call the tool and OMIT the id "
            "field entirely from its arguments — it is auto-filled from the "
            "resolved context. Do not guess it.",
        ),
        _TERMINOLOGY_BLOCK,
        _RELATIONSHIPS_BLOCK,
    ],
    "scenario_analysis": [
        (
            "REFERENCE / AS-IS / BASE SCENARIO",
            "In the current territory, 'scenario di riferimento', 'scenario base', "
            "'situazione attuale', 'scenario as-is' and 'situazione as-is' all refer "
            "to the same designated base scenario. For any of these requests, call "
            "get_base_scenario first, then use its returned ID to resolve that exact "
            "scenario in the scenario list and retrieve its details. Do not treat "
            "these phrases as separate scenarios or select a different scenario "
            "because its name sounds more relevant. If the user asks about the "
            "scenario's evaluation, follow the existing-scenario evaluation rules.",
        ),
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
            "first list_available_entities with entity_types=['scenarios'] (skip "
            "if scenarios are already in prior results — if scenarios haven't been "
            "listed yet this session and the user's description could plausibly "
            "match a saved scenario, call it before assuming none exists), then "
            "get_context_ids with the user's intent.\n\n"
            "  - Once the object is resolved, use get_context_details to retrieve "
            "its stored information (description, metadata, relationships, other "
            "attributes).\n\n"
            "  - ALWAYS assume a request about an existing scenario is also a "
            "request about its evaluation results, even if the user asks only "
            "for general information or mentions the scenario by name/id. After "
            "get_context_details has retrieved the scenario (either earlier in "
            "this turn or in a previous one), call analyze_scenario_results to "
            "report its evaluation and available per-constraint details, and "
            "show the corresponding chart as described below. Include relevant "
            "stored scenario information as requested, but never substitute it "
            "for the evaluation results.\n\n"
            "  - show_analysis_widget builds ONE of four widgets, chosen via its "
            "widget_type argument: 'kpi_comparison', 'comparison_plot', "
            "'load_plot', or 'capacity_plot'. Selection rules:\n\n"
            "    * When calling analyze_scenario_results for a COMPARISON between "
            "two scenarios, you MUST also call show_analysis_widget with "
            "widget_type='comparison_plot' in the same turn (before or after "
            "analyze_scenario_results, not instead of it). This produces the "
            "histogram widget; analyze_scenario_results produces the text — both "
            "are needed.\n\n"
            "    * For a SINGLE existing scenario, you MUST call "
            "analyze_scenario_results and also call "
            "show_analysis_widget with widget_type='load_plot' in the same turn. "
            "This is the general-purpose graphical result and must accompany "
            "the evaluation information whenever the user asks about that "
            "scenario. Do NOT use widget_type='load_plot' for comparisons.\n\n"
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
            "       - Identify the parameters the user means with "
            "get_configuration_parameters — ask only for what you need: pass "
            "`names` when you can already name them, or `search` / `category` for a "
            "topic (e.g. search='parking'); call it with no arguments only to "
            "answer 'what can I change?'. Skip the call if those parameters' "
            "records (name, kind, current, allowed) are already in this turn's "
            "observations or prior results. Users usually use the Italian "
            "label, never the technical name.\n"
            "       - Parameters are NOT all numbers. Each record has a `kind` that "
            "decides the value to pass in `values` (keyed by the record's `name`):\n"
            "           * scalar -> a number within allowed min/max.\n"
            "           * categorical -> exactly one of allowed `values` as text "
            "(e.g. 'rainy'), or null to remove the filter (all). Never a list.\n"
            "           * distribution -> a [low, high] range within allowed min/max; "
            "if the user gives a single number for it, pass the number (it becomes "
            "the central value) and say so in your answer.\n"
            "         For relative requests DO NOT do the arithmetic yourself — pass "
            'an operation: {"multiply": 2} (\'double\'), {"percent": 20} '
            "('+20%'; negative to reduce), {\"add\": 300} ('300 more'). They work on "
            "scalars and on both ends of a range.\n"
            "       - If the user names a parameter but gives no target value or size of "
            "change, or the value they gave is not allowed, do NOT guess and do not "
            "call create_new_temp_scenario: finish with ONE short question that "
            "quotes the parameter's label, its current value and what is allowed "
            "(range and unit for numbers; the list of choices for categorical ones; "
            "low and high for ranges), all taken from the observation.\n"
            "       - Call create_new_temp_scenario with the parameter-name -> value "
            "mapping. This tool needs NO user confirmation and NEVER takes a "
            "name or description — do not ask the user for either at this stage.\n"
            "       - After create_new_temp_scenario returns created=true, its "
            "graphical result (the load plot of the new scenario) is displayed "
            "automatically: do NOT call show_analysis_widget for it. Only if the "
            "user later explicitly asks for another chart of that temporary "
            "scenario (e.g. the capacity plot), call show_analysis_widget with "
            "the returned scenario_id passed explicitly in scenario_ids (never "
            "via current_context).\n"
            "       - ONE AT A TIME: only one temporary scenario can exist at a "
            "time, and only one scenario may be previewed per request. If the "
            "user asks for several scenarios at once, evaluate only the first "
            "and tell them to ask for the next one afterwards. If the result has "
            "already_pending=true, nothing was created: tell the user a "
            "temporary scenario is still waiting to be saved and ask whether to "
            "save it first or discard it. Call create_new_temp_scenario again "
            "with replace_pending=true ONLY if they explicitly choose to discard "
            "it.\n"
            "       - If the result has created=false, nothing was created or "
            "evaluated: read `problems` (each lists the allowed values). Retry once "
            "only if the fix is unambiguous (e.g. the right name for a label); "
            "otherwise finish by asking the user, quoting the allowed values. Never "
            "present a created=false result as an evaluated scenario.\n"
            "       - Only if the user separately and explicitly asks to "
            'save/keep this scenario permanently (e.g. "save it", "keep this '
            'one", "make it official") — and only if their role permits saving '
            "and create_new_temp_scenario has already run earlier this session — "
            "ask for a name (and optionally "
            "a description, and optionally an associated proposal) and then call "
            "create_new_scenario per CREATE / EDIT / DELETE A SCENARIO below.\n"
            "       - When you finish after create_new_temp_scenario returned "
            "created=true, explicitly tell the user the scenario is temporary "
            "and unsaved, in addition to reporting the evaluation results "
            "(sustainability index and per-constraint breakdown) from the "
            "Observation. Only if their role permits saving, also tell them it "
            "may be lost if they do not save it. For a viewer, do not offer "
            "saving as an option or invite them to save it.",
        ),
        (
            "CREATE / EDIT / DELETE A SCENARIO",
            "create_new_scenario here means SAVING an already-previewed temporary "
            'scenario permanently (see EVALUATE A NEW / "WHAT-IF" SCENARIO above) '
            "— it is never the right tool for previewing/evaluating a new what-if "
            "scenario. Extract only name/description details the user actually "
            "typed. Never invent details, never suggest your own mitigation ideas "
            "or strategies as arguments.\n\n"
            "ONE AT A TIME: save only ONE scenario per request, and only the "
            "single temporary scenario that is currently pending. If the user "
            "asks for several, handle only the first and tell them to ask for "
            "the next one afterwards.\n\n"
            "PERMISSION RULE: if the current user role is viewer (or "
            "create_new_scenario appears in the role-unavailable tools list), "
            "they cannot permanently save, create, edit, or delete scenarios. "
            "If they explicitly ask to save/promote a preview or create a "
            "permanent scenario, tell them plainly that their role does not "
            "permit it and that an editor, multieditor, or admin is required. "
            "Do NOT call a write tool, ask for a name/description/proposal, or "
            "otherwise collect save details. Temporary evaluation remains "
            "available when requested.\n\n"
            "create_new_scenario takes an OPTIONAL PROPOSAL id (parent) — only "
            "include it if the user named or clearly implied a proposal to "
            'associate the scenario with (e.g. "link it to the parking '
            'proposal", or a proposal was the obvious subject of this session); '
            "unlike other parent ids, do not go looking for one or ask the user for "
            "it if they never mentioned a proposal — leave it out entirely. If "
            "they did name one, resolve it with list_available_entities "
            "(entity_types=['proposals']) then get_context_ids. "
            "edit_scenario and delete_scenario need their own SCENARIO id (the "
            "target itself). NEVER type/guess/pattern-match an id string yourself:\n"
            "  a. Does the id already appear as an EXPLICIT id string (not a name) "
            "in the user message, the scratchpad, or prior results? If yes, use it "
            "directly.\n"
            "  b. Otherwise, call list_available_entities with "
            "entity_types=['scenarios'] first (skip if scenarios are already in "
            "prior results), THEN get_context_ids — do not call the "
            "edit/delete tool until that id is available. Once resolved, call the "
            "tool and OMIT the id field entirely from its arguments — it is "
            "auto-filled from the resolved context. Do not guess it.",
        ),
        _RELATIONSHIPS_BLOCK,
    ],
    "territory": [
        (
            "AVAILABLE TERRITORIES",
            "When the user asks which localities, destinations, or territories are "
            "available, treat 'località', 'destinazione', and 'territorio' as "
            "synonyms and answer directly from the Available territories in the "
            "context. List those names only; do not ask which problem/proposal/"
            "scenario area they mean, and do not claim the list is unavailable. "
            "If the list is empty, ask which territory they mean instead of "
            "inventing names.",
        ),
    ],
    "general": [
        (
            "GENERAL QUESTION / ONLINE FACTS",
            "For a factual question that depends on current or externally "
            "verifiable information, call web_search and base the answer on its "
            "result, citing the returned source URLs. Use "
            "general_question_response only for broad, creative, or opinion-based "
            "answers that do not need external verification. Before either, "
            "double-check the request is not better answered by platform data, "
            "explain_workflow, or lookup_glossary.",
        ),
    ],
}
