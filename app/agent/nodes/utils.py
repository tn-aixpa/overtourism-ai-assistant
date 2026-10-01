import logging
from typing import Any, Dict

from langgraph.types import Command

from app.agent.state import AgentState
from app.tools.tool_schema import ToolDefinition
from app.utils.common import strip_plot_data

logger = logging.getLogger(__name__)


def request_tier_consent(state: AgentState, tier: str, resume_goto: str) -> Command:
    """Pause the turn to ask the user for one-time consent to use `tier`.

    Call this from any node that is about to enter or delegate into a
    gated tier (state.cognitive.has_valid_tier_consent(tier) is False) —
    today that's tool_executor_node, when the reasoner selects a
    delegate_to_<tier> tool; later, also the top-level router when it
    wants to route a whole turn into a gated tier directly, before any
    tool has been chosen.

    `resume_goto` is the node WAIT_USER_INPUT should return control to once
    the user confirms. tool_executor_node passes "tool_executor" (re-running
    the same gate, which now passes since consent was just granted); a
    router-driven request would pass whatever node starts that tier's own
    reasoning loop.
    """
    state.cognitive.pending_tier_consent = tier
    state.cognitive.tier_consent_resume_goto = resume_goto
    return Command(update=state, goto="WAIT_USER_INPUT")


_ID_RESOLUTION_MAP = {
    # parent references (create)
    "create_new_proposal": ("problem_id", "problems"),
    "create_new_scenario": ("proposal_id", "proposals"),
    # target references (edit / delete)
    "edit_problem": ("problem_id", "problems"),
    "delete_problem": ("problem_id", "problems"),
    "edit_proposal": ("proposal_id", "proposals"),
    "delete_proposal": ("proposal_id", "proposals"),
    "edit_scenario": ("scenario_id", "scenarios"),
    "delete_scenario": ("scenario_id", "scenarios"),
}

# Hard cap on how many tool results we keep in memory per session. This is a
# second line of defense on top of the prompt-side truncation in
# build_prior_results_block: without it, state.cognitive.tool_results grows
# forever for the lifetime of a session (it's kept intentionally across
# turns so the ReAct reasoner can see what already ran), which bloats both
# the in-memory AgentState and the JSON dumped to logs/state_<id>.json.
MAX_STORED_TOOL_RESULTS = 30


def _resolve_referenced_id(
    state: AgentState, tool_name: str, tool_arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """If the tool needs an id (its own target id, or a parent id) that
    wasn't explicitly provided, try to fill it in from IDs already resolved
    by get_context_ids earlier in the plan. Only auto-fills when exactly one
    candidate is available — multiple or zero candidates are left for the
    missing-parameter check to surface, rather than guessed."""
    mapping = _ID_RESOLUTION_MAP.get(tool_name)
    if not mapping:
        return tool_arguments

    param_name, context_key = mapping
    if tool_arguments.get(param_name):
        return tool_arguments

    candidates = (state.cognitive.current_context or {}).get(context_key, [])
    if len(candidates) == 1:
        tool_arguments = dict(tool_arguments)
        tool_arguments[param_name] = candidates[0]
        logger.info(
            f"Auto-resolved '{param_name}'={candidates[0]!r} from current_context for '{tool_name}'"
        )

    return tool_arguments


def _missing_required_params(tool_def: ToolDefinition, args: Dict[str, Any]) -> list:
    """Return the list of required parameter names that are missing or empty."""
    missing = []
    for param in tool_def.parameters:
        if not param.required:
            continue
        value = args.get(param.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(param.name)
    return missing


def _ensure_data_cached(
    state: AgentState, current_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Make sure `state.cognitive.context_cache` has, for every problem_id,
    proposal_id, and scenario_id in `current_context`, the base details
    (and, for scenarios only, evaluation_data). Fetches only what's missing."""
    from app.tools.executor_backend_tools import (
        get_data_from_context,
        get_evaluation_data,
    )

    cache = state.cognitive.context_cache

    to_fetch = {
        kind: [
            item_id
            for item_id in current_context.get(kind, [])
            if f"{kind} {item_id}" not in cache
        ]
        for kind in ("problems", "proposals", "scenarios")
    }

    if any(to_fetch.values()):
        fetched = get_data_from_context.invoke(
            {"current_context": to_fetch, "territory": state.territory}
        )
        cache.update(fetched.get("retrieved", {}))

    # Evaluation data only applies to scenarios
    scenario_ids = current_context.get("scenarios", [])
    missing_eval_ids = [
        sid
        for sid in scenario_ids
        if "evaluation_data" not in cache.get(f"scenarios {sid}", {})
    ]
    if missing_eval_ids:
        fetched_evals = get_evaluation_data.invoke(
            {
                "current_context": {"scenarios": missing_eval_ids},
                "territory": state.territory,
            }
        )
        for key, eval_data in fetched_evals.items():
            if key in cache:
                # Never let the heavy raw plot arrays enter long-lived
                # state — see strip_plot_data's docstring. Nothing in the
                # current codebase reads plot_data back out of the cache.
                cache[key]["evaluation_data"] = strip_plot_data(eval_data)

    state.cognitive.context_cache = cache
    return cache


def _trim_tool_results(state: AgentState) -> None:
    """Evict the oldest tool_results entries once we're over the cap.

    Never evicts a key produced by the scratchpad currently in progress —
    generate_output_message_node needs those to build the final answer.
    """
    results = state.cognitive.tool_results
    protected = set(state.cognitive.current_turn_result_keys())

    while len(results) > MAX_STORED_TOOL_RESULTS:
        for key in results:  # dicts preserve insertion order -> oldest first
            if key not in protected:
                del results[key]
                break
        else:
            # Everything remaining belongs to the current turn; stop rather
            # than evict something generate_output_message_node still needs.
            break
