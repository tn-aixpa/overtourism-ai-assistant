import json
from typing import Dict, Any, List

from app.agent.state import AgentState, ReActStep
from app.agent.nodes import route_groups as rg
from app.prompts.react_guidelines import (
    UNIVERSAL_PRE,
    UNIVERSAL_POST,
    GUIDELINE_BLOCKS,
)
from app.utils.llm import llm_interaction, format_messages
from app.utils.common import (
    build_prior_results_block,
    condense_for_matching,
    truncate_for_prompt,
    _max_chars_for_tool,
)

# Stable rendering order for domain guideline blocks when more than one
# applies at once (only happens while a LOCATION second_level isn't
# resolved yet — see route_groups.guideline_groups) — keeps the assembled
# prompt deterministic across calls instead of depending on set iteration
# order.
_BLOCK_ORDER = [
    "system_info",
    "indexes",
    "problem",
    "proposal",
    "scenario_analysis",
    "general",
]


def _assemble_guidelines(state: AgentState) -> str:
    """Build the GUIDELINES section scoped to the current route instead of
    dumping every domain's rules into every call — see
    app.prompts.react_guidelines module docstring for why. Falls back to
    every block if the route isn't resolved (matches
    route_groups.resolve_allowed_tools' "don't restrict what we can't
    confidently scope" behavior for an unrouted turn)."""
    active_keys = rg.guideline_groups(
        state.cognitive.top_level_route, state.cognitive.second_level_route
    )
    if not active_keys:
        active_keys = set(_BLOCK_ORDER)

    blocks = list(UNIVERSAL_PRE)
    for key in _BLOCK_ORDER:
        if key in active_keys:
            blocks.extend(GUIDELINE_BLOCKS[key])
    blocks.extend(UNIVERSAL_POST)

    lines = []
    for i, (title, body) in enumerate(blocks, start=1):
        lines.append(f"{i}. {title} — {body}")
    return "\n\n".join(lines)


def _format_scratchpad(scratchpad: List[ReActStep]) -> str:
    """Render this turn's Thought/Action/Observation history so far, in the
    classic ReAct transcript style. Empty on the first step of a turn."""
    if not scratchpad:
        return "(none yet — this is the first step of this turn)"

    lines = []
    for i, step in enumerate(scratchpad, start=1):
        if step.thought:
            lines.append(f"Thought {i}: {step.thought}")
        if step.tool_name:
            lines.append(
                f"Action {i}: {step.tool_name}({json.dumps(step.tool_arguments, default=str)})"
            )
        if step.observation is not None:
            # Condense (item-aware) first, THEN cap by characters as a last
            # resort. Dumping the raw observation and cutting the resulting
            # string at a fixed character count can slice a list mid-object
            # (e.g. show 1.5 of 2 problems), and the model reads that partial
            # list as the complete answer — a direct source of undercounting
            # / hallucinated "there is only 1" type answers. condense_for_
            # matching keeps every item's core fields intact and only drops
            # items past a generous cap, always saying so explicitly via a
            # "note" field, so the model knows more exist instead of
            # silently seeing less than what's really there.
            condensed = condense_for_matching(step.observation)
            max_chars = _max_chars_for_tool(step.tool_name, 1200)
            obs = truncate_for_prompt(condensed, max_chars)
            lines.append(f"Observation {i}: {obs}")
        elif step.status:
            lines.append(f"Observation {i}: [{step.status}]")
    return "\n".join(lines)


def react_step(
    state: AgentState,
    tools_for_llm_enabled: List[Dict[str, Any]],
    mode_unavailable_tool_names: List[str],
) -> str:
    """
    Run a single ReAct reasoning step: given the conversation, everything
    already collected this turn (the scratchpad), and long-term memory of
    prior tool results this session, decide either the NEXT single action to
    take or that the agent is ready to finish the turn.

    This is called once per Thought/Action/Observation cycle — NOT once per
    turn — so unlike the old up-front planner, each decision is made with
    full knowledge of every observation gathered so far this turn.

    `mode_unavailable_tool_names`: tools genuinely absent this session for
    an execution-mode reason (currently: widget/chart tools outside
    standalone mode) — NOT tools merely out of scope for the current
    routing domain. Routing-scoped-out tools aren't passed here at all and
    aren't mentioned to the model; only routing (app.agent.nodes.router)
    decides what's in-scope this turn, and it already ran before this call
    (see _assemble_guidelines / TOOL AVAILABILITY guideline for why
    conflating the two would reintroduce a "this tool is unavailable" false
    message for what's actually just a routing/topic mismatch).
    """

    message = (state.get_last_user_message() or "").content

    history = state.get_reasoning_context()
    if history and history[-1].get("content") == message:
        history = history[:-1]
    history_block = format_messages(history) if history else "None"

    available_tools_json = json.dumps(tools_for_llm_enabled, indent=2)

    # Long-term memory (results from earlier turns this session).
    prior_results_block = build_prior_results_block(state.cognitive.tool_results)
    # Working memory (this turn's own Thought/Action/Observation history).
    scratchpad_block = _format_scratchpad(state.cognitive.scratchpad)

    guidelines_block = _assemble_guidelines(state)

    prompt = f"""
You are an assistant for a digital twin platform named AIxPA related to tourism management.

You operate in a ReAct loop: at each turn you either take ONE action (call a single tool)
and observe its result, or you finish with a message. You are being called once per step —
you will be called again with the new observation appended, so you do NOT need to plan
multiple steps ahead. Decide only the SINGLE best next step given everything below.

This conversation has already been routed to a specific area of the platform (reflected in
which tools are listed as available below) — reason within that area; you do not need to
(and should not) re-decide which area this is, that has already been handled upstream.

============================================================
GUIDELINES (apply in order — stop at the first that matches)
============================================================

{guidelines_block}

============================================================
OUTPUT FORMAT
============================================================
Return ONLY ONE JSON object, no markdown, no extra text, matching exactly one of these shapes:

To take an action:
{{"thought": "<your brief reasoning for this single next step>", "action": "tool", "tool_name": "<name>", "arguments": {{}}}}

To finish the turn (covers: normal answers, clarifications, out-of-scope, tool-unavailable):
{{"thought": "<your brief reasoning>", "action": "finish", "message": "<message for the user>"}}

============================================================
CONTEXT
============================================================
Tools available in the current execution mode (full schemas — use these for arguments):
{available_tools_json}

Tools that exist in the system but are NOT available in this execution mode (genuinely
absent, not just out of scope for this area — names only; if the request needs one of
these, finish per the TOOL AVAILABILITY guideline):
{json.dumps(mode_unavailable_tool_names, indent=2) if mode_unavailable_tool_names else "None"}

Prior tool results from earlier in this session (long-term memory — use for argument
resolution, skip re-running a tool if its result is already here):
{prior_results_block}

Conversation so far:
{history_block}

New user message:
"{message}"

This turn's Thought/Action/Observation history so far (working memory for THIS message only):
{scratchpad_block}

Return ONLY valid JSON.
"""

    return llm_interaction(state, prompt, lightweight_llm=False).strip()

