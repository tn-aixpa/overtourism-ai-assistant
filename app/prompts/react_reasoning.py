import json
from typing import Dict, Any, List

from app.agent.state import AgentState, ReActStep
from app.utils.llm import llm_interaction, format_messages
from app.utils.common import build_prior_results_block


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
            obs = json.dumps(step.observation, indent=2, default=str)
            if len(obs) > 1200:
                obs = (
                    obs[:1200]
                    + f"\n... [truncated, {len(obs) - 1200} more characters omitted]"
                )
            lines.append(f"Observation {i}: {obs}")
        elif step.status:
            lines.append(f"Observation {i}: [{step.status}]")
    return "\n".join(lines)


def react_step(
    state: AgentState,
    tools_for_llm: List[Dict[str, Any]],
    tools_for_llm_enabled: List[Dict[str, Any]],
) -> str:
    """
    Run a single ReAct reasoning step: given the conversation, everything
    already collected this turn (the scratchpad), and long-term memory of
    prior tool results this session, decide either the NEXT single action to
    take or that the agent is ready to finish the turn.

    This is called once per Thought/Action/Observation cycle — NOT once per
    turn — so unlike the old up-front planner, each decision is made with
    full knowledge of every observation gathered so far this turn.
    """

    message = (state.get_last_user_message() or "").content

    history = state.get_reasoning_context()
    if history and history[-1].get("content") == message:
        history = history[:-1]
    history_block = format_messages(history) if history else "None"

    available_tools_json = json.dumps(tools_for_llm_enabled, indent=2)
    enabled_names = {t["function"]["name"] for t in tools_for_llm_enabled}
    unavailable_tool_names = [
        t["function"]["name"]
        for t in tools_for_llm
        if t["function"]["name"] not in enabled_names
    ]

    # Long-term memory (results from earlier turns this session).
    prior_results_block = build_prior_results_block(state.cognitive.tool_results)
    # Working memory (this turn's own Thought/Action/Observation history).
    scratchpad_block = _format_scratchpad(state.cognitive.scratchpad)

    prompt = f"""
You are an assistant for a digital twin platform named AIxPA related to tourism management.

You operate in a ReAct loop: at each turn you either take ONE action (call a single tool)
and observe its result, or you finish with a message. You are being called once per step —
you will be called again with the new observation appended, so you do NOT need to plan
multiple steps ahead. Decide only the SINGLE best next step given everything below.

============================================================
GUIDELINES (apply in order — stop at the first that matches)
============================================================

1. TOOL AVAILABILITY — if answering would require a tool listed under "Tools that exist but
   are NOT available in this mode" below, finish immediately with a message explaining the
   current context doesn't support that request.

2. GREETING / GENERAL QUESTION — if the message (and scratchpad so far, if any) is just a
   greeting, thank-you, small talk, or a general "what can you do" question, and no tool has
   been called yet this turn, call get_system_capabilities.

3. ON-TOPIC CHECK — the platform covers tourism management, overtourism, mobility, problems,
   proposals, scenarios, and related decision-support. If the message is clearly about
   something else, finish with a message saying so.

4. DEFINITIONS — if the user asks what a term means, or uses vocabulary that might be a
   platform concept (e.g. "what is a scenario?"), call lookup_glossary. You may also call it
   first if you're unsure whether the user means a problem, proposal, or scenario.

5. DETAILS ABOUT SOMETHING SPECIFIC — if the user explicitly refers to an existing
   problem, proposal, or scenario:

    - If it is referred to by name or description rather than by an explicit id, and it
     has not already been resolved into current_context (check the scratchpad and prior
     results below), resolve it step by step: first the matching list_available_* tool
     (skip if already in prior results), then get_context_ids with the user's intent and
     that source tool.

    - Once the object is resolved, use get_context_details to retrieve its stored
     information (e.g. description, metadata, relationships, and other attributes).

    - If the user asks to explain, summarize, compare, or interpret scenario evaluation
     results (such as metrics, indicators, charts, graphs, simulation outputs, or
     comparisons between scenarios), call analyze_scenario_results. This tool must only be
     used after get_context_details has retrieved the relevant scenario data (either
     earlier in this turn or in a previous one).

    - Do not use analyze_scenario_results when the user only wants general information about
     a problem, proposal, or scenario; answer directly from the data returned by
     get_context_details.

6. CREATE / EDIT / DELETE — map the request to ONE of: create_new_problem, create_new_proposal,
   create_new_scenario, edit_problem, edit_proposal, edit_scenario, delete_problem,
   delete_proposal, delete_scenario.
   Extract only name/description details the user actually typed. Never invent details, never
   suggest your own mitigation ideas or strategies as arguments.

   Every one of these 9 tools needs an id. NEVER type/guess/pattern-match an id string
   yourself. The user almost never knows or types the literal id — they refer to problems,
   proposals, scenarios by name or description (e.g. "the parking problem"). Work it out step
   by step:
     a. Does the id the tool needs already appear as an EXPLICIT id string (not a name) in the
        user message, the scratchpad, or prior results? If yes, use it directly.
     b. Otherwise, which id does the tool need?
        - create_new_proposal, edit_proposal, delete_proposal → a PROBLEM id (parent, or
          edit/delete target's own id — edit/delete only need their own id unless the parent
          is being changed)
        - create_new_scenario, edit_scenario, delete_scenario → a PROPOSAL id likewise
        - create_new_problem → no parent id needed
        - edit_problem, delete_problem → the PROBLEM id (the target itself)
     c. If not yet resolved, call the matching list_available_* tool first (skip if already
        present in prior results), THEN get_context_ids — do not call the create/edit/delete
        tool until that id is available. Once resolving is done, call the create/edit/delete
        tool and OMIT the id field entirely from its arguments — it is auto-filled from the
        resolved context. Do not guess it.

7. NOTHING ABOVE APPLIED — finish with a clarifying question.

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

Tools that exist in the system but are NOT available in this mode (names only — if the
request needs one of these, finish per guideline 1):
{json.dumps(unavailable_tool_names, indent=2) if unavailable_tool_names else "None"}

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
