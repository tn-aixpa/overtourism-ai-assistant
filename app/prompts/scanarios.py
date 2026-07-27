from app.utils.llm import llm_interaction
from app.agent.state import AgentState

# app/prompts/scanarios.py
import copy
from app.utils.llm import llm_interaction
from app.utils.common import truncate_for_prompt
from app.agent.state import AgentState


def analyze_scenario(state: AgentState, query: str):
    context_block = state.cognitive.context_cache

    prompt = f"""You are an analyst for a tourism digital twin platform.
    Answer the following question using ONLY the data provided below.
    If the data does not contain enough information to answer (including if it was
    truncated for length), say so explicitly — do not infer or speculate.
    Be concise and factual. Use a neutral, professional tone.
    
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
    context_block = state.cognitive.context_cache

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

    prompt = f"""You are an analyst for a tourism digital twin platform.
Write a Markdown in {state.user_lang} report using EXACTLY these three top-level headings, in this order:

# Simulation description Report
Briefly explain, in plain language and using ONLY the glossary definitions provided below,
what simulations are on this platform what "sustainability" and "uncertainty" mean in this context.

# General simulation results
Give a general, high-level summary of the overall sustainability and results of
the simulation(s), explicitly citing the sustainability_index value(s) from the
evaluation data below. Also metion if there are and index_diffs (that represent
what changed from the base scenario).

# Detailed results
Describe each sustainability constraint found in the evaluation data below, one
by one, with its value(s). {comparison_instruction}

Use ONLY the data provided below. If some data is missing or was truncated for
length, say so explicitly rather than inferring or speculating. Be concise,
factual, and use a neutral, professional tone.

Glossary definitions:
{glossary_block}

Scenario evaluation data:
{context_block}

Report:"""

    return llm_interaction(state, prompt, lightweight_llm=True)
