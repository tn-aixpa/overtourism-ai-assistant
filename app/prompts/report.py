import json
import logging
import re

from app.utils.llm import llm_interaction
from app.agent.state import AgentState
from app.utils.common import truncate_for_prompt
from app.utils.knowledge import build_terminology_block

# Scenario evaluation data is the core content of the report, so give it a
# much larger budget than the default per-entry cap (DEFAULT_MAX_CHARS_PER_ENTRY,
# used for tool-result injection elsewhere) — trimmed by enforce_prompt_budget
# downstream if the overall prompt still ends up too large.
MAX_CONTEXT_BLOCK_CHARS = 12_000

# A report can cover several problems/proposals/scenarios at once, each with
# its own chapter, so give it a lot more headroom than the short
# single-answer generations elsewhere in this module use by default.
REPORT_MAX_TOKENS = 4096

logger = logging.getLogger(__name__)

# Shape returned by generate_report regardless of what the LLM actually
# produced, so callers (execute_report_generation / the PDF renderer) never
# have to special-case a missing key.
_EMPTY_REPORT_CONTENT: dict = {
    "introduction": "",
    "problems": [],
    "proposals": [],
    "scenarios": [],
    "conclusion": "",
}


def generate_report(
    state: AgentState,
    current_context: dict,
    glossary_matches: list | None = None,
):
    """Generate the structured content of a report: a short introduction,
    one chapter per problem (if any), one per proposal (if any), a
    scenarios chapter with description + evaluation results for each
    scenario, and — unless the report is about a single scenario and
    nothing else — a closing "Conclusion" chapter summarizing the document.

    Returns a plain-data dict (no HTML, no markdown — just prose strings and
    small lists) that the caller turns into the actual document. The
    chapter structure/order/headings are decided here from the real
    problem/proposal/scenario ids in `current_context` (and their names in
    context_cache), never from the LLM's response, so a malformed or
    partial model answer can degrade the content of a chapter but can never
    scramble the shape of the report.
    """
    problem_ids = current_context.get("problems", []) or []
    proposal_ids = current_context.get("proposals", []) or []
    scenario_ids = current_context.get("scenarios", []) or []

    if not (problem_ids or proposal_ids or scenario_ids):
        return dict(_EMPTY_REPORT_CONTENT)

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

    # A conclusion only earns its place when there's more than a single,
    # standalone scenario to sum up — skip it when the whole report is
    # exactly one scenario and nothing else.
    single_scenario_only = (
        len(scenario_ids) == 1 and not problem_ids and not proposal_ids
    )
    needs_conclusion = not single_scenario_only

    terminology_block = build_terminology_block(glossary_block, context_block)

    schema_lines = ['  "introduction": "<string>"']
    if problem_ids:
        schema_lines.append(
            '  "problems": [{"id": "<problem_id>", "text": "<string>"}, ...]'
        )
    if proposal_ids:
        schema_lines.append(
            '  "proposals": [{"id": "<proposal_id>", "text": "<string>"}, ...]'
        )
    if scenario_ids:
        schema_lines.append(
            '  "scenarios": [{"id": "<scenario_id>", "narrative": "<string>", '
            '"constraints": [{"name": "<string>", "detail": "<string>"}, ...]}, ...]'
        )
    if needs_conclusion:
        schema_lines.append('  "conclusion": "<string>"')
    schema_block = "{\n" + ",\n".join(schema_lines) + "\n}"

    conclusion_rule = (
        '- "conclusion": a short closing chapter that sums up the report as a '
        "whole, tying together what was covered in the chapters above — do not "
        "introduce new data here.\n"
        if needs_conclusion
        else ""
    )

    prompt = f"""You are an analyst for a tourism digital twin platform, writing the content
of a formal report in {state.user_lang}. Respond with ONLY a valid JSON object — no
markdown code fences, no HTML tags, no explanatory text before or after — matching
EXACTLY this shape (include every key shown, no other keys):

{schema_block}

CONTENT RULES:
- Every value is plain prose meant to be printed in a document: full sentences, no
  markup of any kind (no HTML tags, no markdown *, #, or - characters, no bullet
  characters). Use "\\n\\n" only where you genuinely want a paragraph break.
- All numeric sustainability/index/constraint values MUST be expressed as percentages
  (e.g. "70.3%"), NEVER as raw 0-1 decimals (e.g. never "0.703"). Convert every such
  value before writing it.
- Confidence intervals/margins must also be converted to percentage points
  (e.g. "±1.5 percentage points"), not decimal form.
- "introduction": briefly explain, in plain language and using ONLY the glossary
  definitions provided below, what simulations are on this platform and what
  "sustainability" and "uncertainty" mean in this context. Keep it general — the
  specific problems/proposals/scenarios are each covered in their own chapter below.
- For each entry under "problems"/"proposals": a few well-structured paragraphs
  describing that problem/proposal, using ONLY the data provided below (name,
  description, objective, resources, context, impact, etc. as available for it).
- For each entry under "scenarios": "narrative" is a general summary of that
  scenario (its description, its overall sustainability_index as a percentage, and
  index_diffs vs. the base scenario if present, also as percentages); "constraints"
  is one entry per sustainability constraint found in the evaluation data for that
  scenario, "name" being the constraint's name and "detail" its value(s) as
  percentage(s). {comparison_instruction}
{conclusion_rule}
Use ONLY the data provided below. If some data is missing or was truncated for
length, say so explicitly within the relevant chapter's text rather than inferring
or speculating. Be concise, factual, and use a neutral, professional tone throughout.
{terminology_block}
Glossary definitions:
{glossary_block}

Problem / proposal / scenario data:
{context_block}

Respond with ONLY the JSON object described above, in {state.user_lang}."""

    raw = llm_interaction(
        state, prompt, max_tokens=REPORT_MAX_TOKENS, lightweight_llm=False
    )

    return _parse_report_content(raw, needs_conclusion)


def _parse_report_content(raw: str, needs_conclusion: bool) -> dict:
    """Parse the LLM's JSON response into the report content dict, tolerating
    the usual ```json code-fence wrapping. Falls back to an empty-but-valid
    structure (rather than raising) if the model returns something
    unparsable, so one bad generation degrades to a thin report instead of
    failing report_generation outright."""
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE
    ).strip()

    try:
        content = json.loads(cleaned)
        if not isinstance(content, dict):
            raise ValueError("Report JSON root is not an object")
    except Exception:
        logger.exception("generate_report: failed to parse LLM response as JSON")
        content = {}

    result = dict(_EMPTY_REPORT_CONTENT)
    result["introduction"] = content.get("introduction") or ""
    result["problems"] = content.get("problems") or []
    result["proposals"] = content.get("proposals") or []
    result["scenarios"] = content.get("scenarios") or []
    result["conclusion"] = (content.get("conclusion") or "") if needs_conclusion else ""

    return result
