import logging

from app.utils.llm import llm_interaction
from app.agent.state import AgentState
from app.utils.common import truncate_for_prompt
from app.utils.terminology import build_terminology_block

# Scenario evaluation data is the core content of the report, so give it a
# much larger budget than the default per-entry cap (DEFAULT_MAX_CHARS_PER_ENTRY,
# used for tool-result injection elsewhere) — trimmed by enforce_prompt_budget
# downstream if the overall prompt still ends up too large.
MAX_CONTEXT_BLOCK_CHARS = 12_000

logger = logging.getLogger(__name__)


def analyze_scenario(state: AgentState, query: str, widget_hint: str | None = None):
    context_block = state.cognitive.context_cache

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
    
    Context data:
    {context_block}
    
    Answer:"""

    return llm_interaction(state, prompt, lightweight_llm=True)


def generate_summary(
    state: AgentState,
    scenario_ids: list,
    glossary_matches: list | None = None,
):
    context_block = truncate_for_prompt(
        state.cognitive.context_cache, max_chars=MAX_CONTEXT_BLOCK_CHARS
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
- All numeric sustainability/index/constraint values MUST be expressed as percentages (e.g. "70.3%"), NEVER as raw 0–1 decimals (e.g. never "0.703"). Convert every such value before writing it.
- Confidence intervals/margins must also be converted to percentage points (e.g. "±1.5 punti percentuali" / "±1.5 percentage points"), not decimal form.
- You may use <strong> and <em> for emphasis within any paragraph.
- For the first two sections, use a single <p> tag with the class shown below — no lists needed there.
- For the third section ("Risultati dettagliati"), since you'll be listing multiple constraints, use a <div _ngcontent-ng-c2324380181="" class="small text-muted mb-2"> instead of a <p> for that section's content block, and inside it use a <ul class="mb-0"> with one <li> per constraint. Bold the constraint name at the start of each <li> with <strong>. Do NOT nest <ul>/<li> inside a <p> tag — it is invalid HTML and will be silently broken by the browser.
- Do not use any other tags (no <h1>-<h5>, no <table>, no <img>, no <script>).

<h6 _ngcontent-ng-c2324380181="" class="text-primary mb-3 d-flex align-items-center gap-2">Descrizione simulazione</h6>
<p _ngcontent-ng-c2324380181="" class="small text-muted mb-2">
[fill in: Briefly explain, in plain language and using ONLY the glossary definitions provided below,
what simulations are on this platform and what "sustainability" and "uncertainty" mean in this context.]
</p>

<h6 _ngcontent-ng-c2324380181="" class="text-primary mb-3 d-flex align-items-center gap-2">Risultati generali simulazione</h6>
<p _ngcontent-ng-c2324380181="" class="small text-muted mb-2">
[fill in: Give a general, high-level summary of the overall sustainability and results of
the simulation(s), explicitly citing the sustainability_index value(s) as percentages from the
evaluation data below. Also mention index_diffs if present (what changed from the base scenario, also as percentages).]
</p>

<h6 _ngcontent-ng-c2324380181="" class="text-primary mb-3 d-flex align-items-center gap-2">Risultati dettagliati</h6>
<p _ngcontent-ng-c2324380181="" class="small text-muted mb-2">
[fill in: a <ul class="mb-0"> with one <li> per sustainability constraint found in the evaluation data below,
each starting with the constraint name in <strong>, followed by its value(s) as percentages. {comparison_instruction}]
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
