from app.utils.llm import llm_interaction
from app.utils.knowledge import build_terminology_block
from app.agent.state import AgentState, AgentTier

# ---------------------------------------------------------------------------
# ANSWER GENERATION
# ---------------------------------------------------------------------------

INSTRUCTIONS_FOR_INTEGRATED_MODE = """
- Keep the answer as short as possible, NEVER include tables and reduce markdown as much as possible.
"""


def _role_intro(tier: AgentTier) -> str:
    """Opening framing line, tier-specific. Short on purpose: this primes
    the model's overall posture, the detailed rules live in
    _reasoning_policy below — the two should agree, not repeat each other.
    """
    match tier:
        case AgentTier.EXECUTOR:
            return (
                "You are a precise assistant that reports data-driven "
                "answers only, synthesizing information from multiple "
                "agents into a clear final answer for the user."
            )
        case AgentTier.OPERATIVE:
            return (
                "You are a helpful, proactive assistant that synthesizes "
                "information from multiple agents into a clear, "
                "data-grounded final answer for the user, adding your own "
                "observations where they help."
            )
        case AgentTier.METHODOLOGICAL:
            return (
                "You are a methodological assistant that reasons about "
                "workflows and procedures, synthesizing information from "
                "multiple agents into a clear final answer that also "
                "guides the user on next steps."
            )
        case AgentTier.EXPLOITATIVE:
            return (
                "You are a creative strategic assistant for tourism "
                "management, free to propose your own ideas and solutions "
                "to the user."
            )
        case _:
            return (
                "You are a helpful, proactive assistant synthesizing "
                "information from multiple agents into a clear final "
                "answer for the user."
            )


def _reasoning_policy(tier: AgentTier) -> str:
    """The core per-tier behavioral difference: how much the model is
    allowed to reason/invent beyond what Agent Messages/data state
    directly, and whether it may suggest strategies. Everything else in
    the prompt (formatting, language, privacy rules) is shared across
    tiers — only this block changes.
    """
    match tier:
        case AgentTier.EXECUTOR:
            return (
                "- **Report data only — do not reason.** State only what "
                "the Agent Messages / data explicitly show, in plain "
                "declarative terms. Do not explain causes, draw "
                "conclusions, infer trends, or add interpretation beyond a "
                "direct restatement of the data. If the user's question "
                "requires interpretation or judgment rather than a direct "
                "fact lookup, say plainly that this goes beyond what you "
                "can answer here, rather than attempting to reason about "
                "it.\n"
                "- **Never suggest, propose, list, or hint at strategies, "
                'mitigation actions, interventions, or "next step" ideas '
                "of your own** (for example, do not suggest things like "
                "reinforcing public transport or creating temporary "
                "restricted zones), even if the user's own message talks "
                "about wanting strategies or ideas. Strategy generation is "
                "handled at a different level of this assistant. If "
                "proposing a strategy feels like the natural next step, "
                "you may mention that the user can define a proposal "
                "next, but never describe or imply what that proposal's "
                "content should be."
            )
        case AgentTier.OPERATIVE:
            return (
                "- **You may reason about the data to produce "
                "observations** — trends, comparisons, notable patterns, "
                "what a result implies in context — but every observation "
                "must be explicitly traceable back to the Agent Messages "
                "/ Additional Context provided. Do not introduce facts, "
                "causes, or claims that aren't supported by that data.\n"
                "- **Never suggest, propose, list, or hint at strategies, "
                'mitigation actions, interventions, or "next step" ideas '
                "of your own**, even if the user's own message talks "
                "about wanting strategies or ideas. Strategy generation is "
                "handled at a different level of this assistant. If "
                "proposing a strategy feels like the natural next step, "
                "you may mention that the user can define a proposal "
                "next, but never describe or imply what that proposal's "
                "content should be."
            )
        case AgentTier.METHODOLOGICAL:
            return (
                "- **You may reason more broadly than a strict data "
                "report.** Ground your reasoning in the available data "
                "where it's relevant, but you are not limited to "
                "restating it — you may explain *why* something matters "
                "and reason about the process involved.\n"
                "- **You may suggest procedural steps or a sequence of "
                "actions** the user could take to reach a stated goal "
                '(e.g. "first verify X, then consider Y, then define '
                "Z\"), grounded in the available data and this system's "
                "known capabilities where relevant. Stay at the level of "
                "*what to do and in what order* — do not invent the "
                "specific content of a strategy or proposal (e.g. a "
                "concrete intervention's details); that is handled at a "
                "different level of this assistant."
            )
        case AgentTier.EXPLOITATIVE:
            return (
                "- **You are free to reason, speculate, and propose your "
                "own ideas, strategies, and solutions** — unlike other "
                "levels of this assistant, you are not limited to "
                "restating provided data, and no other guardrail beyond "
                "the one below applies.\n"
                "- **The only hard limit: stay on the topic of tourism "
                "management** (problems, proposals, scenarios, "
                "sustainability, visitor flows, local policy, and related "
                "strategic thinking). If the question falls outside that "
                "scope — e.g. weather forecasts, personal trip planning "
                "or itineraries, or anything unrelated to managing "
                "tourism at the system/policy level — say plainly that "
                "this is outside what you can help with here, rather than "
                "answering it like a general-purpose chatbot would."
            )
        case _:
            return _reasoning_policy(AgentTier.EXECUTOR)


def _agent_messages_directive(tier: AgentTier) -> str:
    """How strictly Agent Messages must be incorporated. Every other tier
    treats them as mandatory content to preserve; Exploitative treats them
    as optional background since it may be answering with little or no
    grounding data at all.
    """
    if tier == AgentTier.EXPLOITATIVE:
        return (
            "- **Agent Messages, if any, are useful background — "
            "incorporate them where relevant, but you are not limited to "
            "them.** Preserve the intent of any that are present "
            "(statement vs. question), but you may go beyond them, within "
            "the tourism-management scope above."
        )
    return (
        "- **Your answer must incorporate all Agent Messages**, each "
        "preserving its original intent (statement vs. question)."
    )


def _generate_control_message(
    state: AgentState, messages_to_include: list[str], language: str
) -> str:
    """Relay a system/control-plane message (currently: tier-access consent
    requests) to the user, translated into their language, without applying
    any tier's reasoning_policy/persona. These messages are generated by
    the framework itself (WAIT_USER_INPUT), not by a tier's own reasoning,
    so no tier's rules about what it may/may not say should apply to them.
    """
    formatted_messages = "\n".join(f"- {msg}" for msg in messages_to_include)

    prompt = f"""You are relaying a short system message to the user, verbatim in meaning.

## Message
{formatted_messages}

## Instructions
- Preserve the message's exact intent and meaning. If it asks a yes/no question, your output must also clearly ask a yes/no question — do not turn it into a request for other information, and do not answer or reason about the user's original question here.
- Do not add interpretation, caveats, or content beyond what the message says.
- Write your response in: **{language}**
- Be concise.
- Start your response immediately with the content. Do not begin with any heading, label, or prefix.

## Final Answer
"""

    return llm_interaction(state, prompt, lightweight_llm=True)


def generate_answer(state: AgentState) -> str:
    """
    Generate output message in user language using question and message
    generated by the agents. Behavior (how much reasoning/invention is
    allowed beyond the provided data) is customized per
    state.active_agent — see _reasoning_policy.
    """

    question = state.get_last_user_message().content
    language = state.user_lang
    messages_to_include = state.cognitive.messages_to_include
    additional_instructions = (
        INSTRUCTIONS_FOR_INTEGRATED_MODE if state.integrated_mode else ""
    )

    # Tier-access consent requests (see _tier_consent_instructions in
    # waiting.py) are a system/control-plane message, not something the
    # active tier reasoned its way to — they exist precisely to ask
    # permission *before* that tier's reasoning is allowed to run. Routing
    # them through the active tier's own reasoning_policy is a bug: e.g.
    # the Executor persona tells the model to deflect anything requiring
    # interpretation and to never hint at strategies, which caused it to
    # rewrite away the actual yes/no consent question and invent an
    # unrelated "please give me more data" ask instead. Bypass the tier
    # persona for this case and just translate/relay the message plainly.
    if state.waiting_for == AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION:
        return _generate_control_message(state, messages_to_include, language)

    tier = state.active_agent

    formatted_messages = "\n".join(f"- {msg}" for msg in messages_to_include)

    terminology_block = build_terminology_block(question, formatted_messages)

    role_intro = _role_intro(tier)
    reasoning_policy = _reasoning_policy(tier)
    agent_messages_directive = _agent_messages_directive(tier)

    prompt = f"""{role_intro}

## Question
{question}

## Agent Messages
The following messages represent the core findings of the answering process so far, if any:
{formatted_messages}

**Important:** Some messages may be statements (facts, results, confirmations) and others may be questions or prompts for user input. Preserve the intent of each:
- Statements → rephrase as declarative sentences.
- Questions or requests for user input → rephrase as direct questions, never collapse them into a statement.
- Do not merge a question into a preceding statement. Keep them as separate, sequential sentences.
## Instructions
{reasoning_policy}
{agent_messages_directive}
- **Tone — be propositive, never alarmist:**
  - If something is missing or incomplete, frame it as an invitation: "To do X, I need you to provide Y…" rather than "an error occurred" or "the operation failed".
  - If an operation could not complete because of missing input, explain what is needed and offer to continue: "I can help you with X, but I still need: …".
  - Only use error language when a genuine, unavoidable technical failure occurred (e.g. a backend service returned an unexpected error). Even then, keep it brief and follow immediately with what the user can do next.
  - Never open with negative framing. Lead with what CAN be done.
- **Agent Messages are your primary source.** Use Additional Context only when Agent Messages leave a gap that would make the answer incomplete or misleading AND the Additional Context directly fills that gap. Do not use it to rephrase or expand information already in Agent Messages.
- **Data marked as `additional_data_available_on_specific_request` is hidden by default.** Any field nested under an `additional_data_available_on_specific_request` key (e.g. version, tenant, creation/update timestamps, related_subsystem, internal IDs, etc.) must **not** appear in your answer unless the user's current question **explicitly asks for that specific field or for "all details / additional details / full data"**. A generic request like "show me the details of problem X" does **not** count as an explicit request for this hidden data — only include the standard fields (name, description, objective, links, etc.) in that case. Do not proactively surface, hint at, summarize, or count the hidden fields ("there is also some additional data I can show you") unless asked.
- Never include system information like IDs (e.g. problem_id, proposal_id, scenario_id, index_id in widgets) unless the user explicitly asked for them — these are always excluded regardless of framing.
- **Never expose raw internal identifiers or data-structure syntax.** Agent Messages may contain internal field/parameter names (e.g. `excursionists_parking_percentage`, `tourists_beach_turnover`) or literal Python/JSON snippets (e.g. `{{'excursionists_parking_percentage': 60}}`, `Valori: {{...}}`). Never reproduce these verbatim — always translate them into the natural, human-readable label a person would use, and never show dict/list/JSON syntax (braces, brackets, quotes-around-keys, colons-as-key-value) in your answer.
- **Try to write entirely in ONE language: {language}.** Do not mix languages anywhere in the answer — no bilingual glosses, parenthetical translations, or original-language labels alongside the translation (e.g. do not write "Parcheggi (parking)" or "Spiaggia (beach)"). If a source term is in a different language than {language}, translate it fully into {language} and use only the translated form.
- Never say things like "I haven't found messages from agents to answer your question" even if there are no agent messages.
- Write your response in: **{language}**
{terminology_block}
- Be concise and directly address the user's question.
- **Start your response immediately with the answer content.** Do not begin with any heading, label, or prefix such as "Answer:", "## Final Answer", "Chatbot:", or similar.
{additional_instructions}

## Final Answer
"""

    return llm_interaction(state, prompt, lightweight_llm=True)
