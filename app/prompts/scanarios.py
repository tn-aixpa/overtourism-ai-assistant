import logging

from app.utils.llm import llm_interaction
from app.agent.state import AgentState
from app.utils.common import truncate_for_prompt
from app.utils.knowledge import build_terminology_block
from app.utils.evaluation_summary import (
    build_legend,
    get_configuration_metadata,
    label_kpis,
)

# Scenario evaluation data is the core content of the report, so give it a
# much larger budget than the default per-entry cap (DEFAULT_MAX_CHARS_PER_ENTRY,
# used for tool-result injection elsewhere) — trimmed by enforce_prompt_budget
# downstream if the overall prompt still ends up too large.
MAX_CONTEXT_BLOCK_CHARS = 12_000

logger = logging.getLogger(__name__)


def _scenario_view(entry: dict, include_plots: bool, state_territory: str) -> dict:
    """One scenario's cache entry reduced to what a prompt needs: identity,
    changes w.r.t. the base scenario and the evaluation as KPIs carrying the
    labels defined in /configuration (kpi_mapper / mapper). The raw (unlabelled)
    KPI dict is dropped so the model never sees two spellings of one figure."""
    evaluation = entry.get("evaluation_data") or {}
    kpis = evaluation.get("kpis_labelled")
    if kpis is None and evaluation.get("data"):
        # Entry cached without labels: label it now from /configuration.
        kpis = label_kpis(
            evaluation["data"], get_configuration_metadata(state_territory)
        )
    view = {
        "scenario_id": entry.get("scenario_id"),
        "name": entry.get("name"),
        "description": entry.get("description"),
        "changes_wrt_base_scenario": entry.get("changes_wrt_base_scenario"),
        "kpis": kpis,
    }
    if include_plots and evaluation.get("plot_summary"):
        view["plot_summary"] = evaluation["plot_summary"]
    return {k: v for k, v in view.items() if v not in (None, "", [], {})}


def build_scenarios_context(
    state: AgentState, scenario_ids: list | None = None, include_plots: bool = False
) -> dict:
    """Cache content for prompts, with scenario entries in the slim, labelled
    form of _scenario_view (other entries — problems, proposals — unchanged)."""
    cache = state.cognitive.context_cache or {}
    wanted = {f"scenarios {sid}" for sid in scenario_ids} if scenario_ids else None
    context = {}
    for key, entry in cache.items():
        if key.startswith("scenarios ") and isinstance(entry, dict):
            if wanted is None or key in wanted:
                context[key] = _scenario_view(entry, include_plots, state.territory)
        elif wanted is None:
            context[key] = entry
    return context



def analyze_scenario(state: AgentState, query: str, widget_hint: str | None = None):
    # Bounded the same way generate_summary/generate_report (below and in
    # app/prompts/report.py) already treat context_cache — this used to
    # f-string the RAW cache dict in unbounded, which (a) had no size cap
    # at all (unlike every other context_cache injection site in this
    # codebase) and (b) rendered as a Python dict repr rather than JSON.
    # Bounding it here is defense-in-depth: context_cache should no longer
    # contain plot_data at all (see app.utils.common.strip_plot_data), but
    # other fields (extras, related_scenario_ids, ...) can still be sizable.
    context_block = truncate_for_prompt(
        build_scenarios_context(state, include_plots=True),
        max_chars=MAX_CONTEXT_BLOCK_CHARS,
    )
    legend_block = truncate_for_prompt(
        build_legend(get_configuration_metadata(state.territory)), max_chars=3000
    )

    visual_note = (
        f"\n    A {widget_hint} will be displayed to the user automatically alongside "
        "your answer, so do NOT claim that charts/visualizations cannot be shown — "
        "you may refer to it (e.g. 'see the chart below') if relevant.\n"
        if widget_hint
        else "\n    No chart or visualization will be displayed alongside your answer — "
        "if the user asked specifically for one, say only the underlying data is "
        "available as text, without speculating about why a chart isn't shown.\n"
    )

    prompt = f"""You are an analyst for a tourism digital twin platform.
    Answer the following question using ONLY the data provided below.
    If the data does not contain enough information to answer (including if it was
    truncated for length), say so explicitly — do not infer or speculate.
    Be concise and factual. Use a neutral, professional tone.
    {visual_note}
    Question: {query}

    How to read the data:
    - "kpis" are the evaluation results. Each has a "label" (the name shown
      in the UI: use it as is) and a "result" already written as a Italian
      phrase with units and uncertainty: quote it, do not recompute or
      rescale numbers. Never mention internal field names or the "role".
    - "plot_summary" describes the load / capacity plots. Each point is one
      simulated day. "points_by_color" holds the number of green / yellow /
      red points, already counted: for questions such as "how many red
      dots" report those counts (and percentages) verbatim, never estimate
      them. "color_legend" explains which index values each colour covers.
    - Labels and axis names from the platform configuration: {legend_block}

    Context data:
    {context_block}
    
    Answer:"""

    return llm_interaction(state, prompt, lightweight_llm=True)


def generate_summary(
    state: AgentState,
    scenario_ids: list,
    glossary_matches: list | None = None,
):
    # The summary is KPI-based: per scenario, only identity, changes w.r.t.
    # the base scenario and the KPIs labelled through /configuration.
    context_block = truncate_for_prompt(
        build_scenarios_context(state, scenario_ids, include_plots=False),
        max_chars=MAX_CONTEXT_BLOCK_CHARS,
    )

    glossary_block = (
        truncate_for_prompt(glossary_matches, max_chars=3000)
        if glossary_matches
        else "No glossary definitions were found for these terms."
    )

    multi_scenario = len(scenario_ids) > 1
    comparison_instruction = (
        "Since there is more than one scenario, for EACH constraint also compare "
        "its values across scenarios, noting differences and which scenario performs "
        "better on that constraint."
        if multi_scenario
        else "Only one scenario is present, so no cross-scenario comparison is needed."
    )

    terminology_block = build_terminology_block(glossary_block, context_block)

    prompt = f"""You are an analyst for a tourism digital twin platform.
Write a HTML **fragment** in {state.user_lang} — do NOT include <!DOCTYPE html>, <html>, <head>, <body>, <title>, or any CDN/stylesheet links. Output ONLY the three heading/content blocks below, filled in. Nothing before the first <h6> and nothing after the final closing tag.

Use EXACTLY these three top-level headings, in this order, with NO other headings, wrappers, or containers added around the whole thing:

FORMATTING RULES:
- The data below lists each scenario's "kpis" as {{label, result}}. Use EXACTLY the "label" as the KPI name (it is what the user sees in the interface) and report its "result" in natural, human-readable Italian prose, keeping its numbers, units and uncertainty exactly as given (never rescale them).
- NEVER write technical field names (such as level, confidence, level_percent, value, share, role, key, kpis) and never write "campo: valore" pairs: translate everything into plain sentences (e.g. "si attesta al 91,7%, con un margine di incertezza di ±0,7 punti percentuali").
- The uncertainty ("incertezza ... punti percentuali") is a margin of error around the figure; explain it simply when you first mention it.
- The KPI with role "overall" is the overall sustainability; the KPI with role "critical" names the constraint that limits sustainability the most. Do not mention the word "role".
- EVERY KPI in the data MUST be mentioned at least once in the summary — none may be omitted, including those that are not about sustainability (e.g. visitors who do not arrive); if such a KPI is zero, say so explicitly in words (e.g. "nessun visitatore rinuncia ad arrivare").
- You may use <strong> and <em> for emphasis within any paragraph.
- For the first two sections, use a single <p> tag with the class shown below — no lists needed there.
- For the third section ("Risultati dettagliati"), since you'll be listing multiple KPIs, use a <div _ngcontent-ng-c2324380181="" class="small text-muted mb-2"> instead of a <p> for that section's content block, and inside it use a <ul class="mb-0"> with one <li> per KPI. Bold the KPI label at the start of each <li> with <strong>. Do NOT nest <ul>/<li> inside a <p> tag — it is invalid HTML and will be silently broken by the browser.
- Do not use any other tags (no <h1>-<h5>, no <table>, no <img>, no <script>).

<h6 _ngcontent-ng-c2324380181="" class="text-primary mb-3 d-flex align-items-center gap-2">Descrizione simulazione</h6>
<p _ngcontent-ng-c2324380181="" class="small text-muted mb-2">
[fill in: Briefly explain, in plain language and using ONLY the glossary definitions provided below,
what simulations are on this platform and what "sustainability" and "uncertainty" mean in this context.]
</p>

<h6 _ngcontent-ng-c2324380181="" class="text-primary mb-3 d-flex align-items-center gap-2">Risultati generali simulazione</h6>
<p _ngcontent-ng-c2324380181="" class="small text-muted mb-2">
[fill in: Give a general, high-level summary of the overall overtourism level and results of
the simulation(s), explicitly citing the overall sustainability KPI and the critical constraint KPI (which constraint it is and how sustainable it is), from the evaluation data below.
If "changes_wrt_base_scenario" is present, also mention what changed compared with the base scenario.]
</p>

<h6 _ngcontent-ng-c2324380181="" class="text-primary mb-3 d-flex align-items-center gap-2">Risultati dettagliati</h6>
<p _ngcontent-ng-c2324380181="" class="small text-muted mb-2">
[fill in: a <ul class="mb-0"> with one <li> per KPI found in the evaluation data below EXCEPT the overall sustainability and the critical constraint KPIs (already covered in the previous section), so that together the two sections cover every KPI,
each starting with the KPI label in <strong>, followed by its result in plain Italian prose. {comparison_instruction}]
</p>

Use ONLY the data provided below. If some data is missing or was truncated for
length, say so explicitly rather than inferring or speculating. Be concise,
factual, and use a neutral, professional tone.
{terminology_block}
Glossary definitions:
{glossary_block}

Scenario evaluation data:
{context_block}

Respond with ONLY the HTML fragment above (h6/p, h6/p, h6/p>ul>li), filled in, following every formatting rule exactly. Do not add a document wrapper, markdown code fences, or any explanatory text before or after."""

    return llm_interaction(state, prompt, lightweight_llm=True)
