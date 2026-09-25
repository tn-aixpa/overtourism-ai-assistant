"""
Tool execution node for the agentic system (Acting half of the ReAct loop).

Executes the single tool the reasoner just selected ("Action"), records the
result on the scratchpad ("Observation"), and routes back to
react_reasoner_node so it can decide the next step with that observation in
hand. This node handles the actual tool invocation and error handling.
"""

import logging
from typing import Any, Dict, Callable
from langgraph.types import Command

from app.agent.state import AgentState, ReActStep, AgentTier, TIERS_REQUIRING_CONSENT
from app.agent.events import publish_action
from app.agent.nodes.utils import (
    _resolve_referenced_id,
    _missing_required_params,
    _trim_tool_results,
    request_tier_consent,
)
from app.tools.tool_registry import get_tool_registry
from app.tools.tool_schema import ToolDefinition
from app.tools.executors.system_utility import execute_lookup_glossary

logger = logging.getLogger(__name__)

# Tools that mutate platform data and therefore require an explicit user
# confirmation (recap of the data about to be submitted) before they run.
CONFIRMATION_REQUIRED_TOOLS = {
    "create_new_problem",
    "create_new_proposal",
    "create_new_scenario",
    "edit_problem",
    "edit_proposal",
    "edit_scenario",
    "delete_problem",
    "delete_proposal",
    "delete_scenario",
}


# Maps a tool to the (parameter, current_context key) used to auto-resolve
# an ID once get_context_ids has run earlier this turn. Covers both
# "parent" references (e.g. a new proposal's problem_id) and "target"
# references (e.g. the problem_id of the problem being edited/deleted) —
# resolution logic is identical in both cases: only fill in when exactly
# one candidate exists in current_context, otherwise leave it for the
# missing-parameter check to catch.
# Maps a mutating tool to the (parameter, context_cache kind) of the object
# it just changed, so tool_executor_node can evict that object's stale
# cache entry right after a successful run (see
# CognitiveState.invalidate_cached_object). Only covers edit/delete: a
# create_* tool produces a brand-new id that can't already be cached.
_CACHE_INVALIDATION_MAP = {
    "edit_problem": ("problem_id", "problems"),
    "delete_problem": ("problem_id", "problems"),
    "edit_proposal": ("proposal_id", "proposals"),
    "delete_proposal": ("proposal_id", "proposals"),
    "edit_scenario": ("scenario_id", "scenarios"),
    "delete_scenario": ("scenario_id", "scenarios"),
}

# Ordinal ranking for AgentTier, lowest-license first — used only to decide
# whether a tool's agent_tier should raise state.active_agent for the rest
# of the turn (see _bump_active_agent). Matches AgentTier's own declaration
# order in app.agent.state.
_TIER_ORDER = [
    AgentTier.EXECUTOR,
    AgentTier.OPERATIVE,
    AgentTier.METHODOLOGICAL,
    AgentTier.EXPLOITATIVE,
]


def _bump_active_agent(state: AgentState, tool_def: ToolDefinition | None) -> None:
    """
    Raise state.active_agent to tool_def.agent_tier if that tier outranks
    whatever active_agent already is this turn — never lowers it.

    active_agent decides the RESPONSE persona/policy generate_answer()
    uses when the turn finishes (see _reasoning_policy in
    answer_generation.py), and — for tiers in TIERS_REQUIRING_CONSENT —
    whether running the tool needs one-time user consent first (checked by
    the caller before this is called). It is reset to the EXECUTOR
    baseline once per turn in initialize_tools, then only ever raised here
    as tools actually run, so a turn that calls e.g. list_available_*
    (EXECUTOR) and then analyze_scenario_results (OPERATIVE) ends up with
    active_agent=OPERATIVE for its final answer even if an EXECUTOR-tier
    tool (like show_analysis_widget) also runs afterwards in the same turn.
    """
    if not tool_def:
        return
    try:
        tool_tier = AgentTier(tool_def.agent_tier)
    except ValueError:
        logger.warning(
            f"Unknown agent_tier '{tool_def.agent_tier}' on tool "
            f"'{tool_def.name}', leaving active_agent unchanged"
        )
        return
    if _TIER_ORDER.index(tool_tier) > _TIER_ORDER.index(state.active_agent):
        logger.info(
            f"Bumping active_agent {state.active_agent} -> {tool_tier} "
            f"(tool '{tool_def.name}')"
        )
        state.active_agent = tool_tier


def execute_selected_tool(
    tool_name: str,
    tool_arguments: Dict[str, Any],
    state: AgentState,
    allow_disabled: bool = False,
) -> Dict[str, Any]:
    """
    Execute a tool with the given arguments.

    Handles dispatching to tool-specific implementations.
    Returns the tool result.

    `allow_disabled`: some tools (e.g. summary_generation) are registered
    with enabled=False purely to keep them out of the normal ReAct
    allowlist (see ToolRegistry.get_all_known_tools), while still being
    callable explicitly — e.g. from the /agent/tool pipeline endpoint. Set
    this to True in that kind of explicit, non-ReAct invocation path.
    """
    logger.info(f"Executing tool: {tool_name} with args: {tool_arguments}")

    # Get the tool definition
    registry = get_tool_registry()
    tool_def = registry.get_tool(tool_name)

    if not tool_def:
        raise ValueError(f"Tool '{tool_name}' not found in registry")

    if not tool_def.enabled and not allow_disabled:
        raise ValueError(f"Tool '{tool_name}' is disabled")

    # Role/mode gating is enforced here too, not just at selection time
    # (ToolRegistry.get_context_tools, consulted by initialize_tools /
    # react_reasoner_node) — this function is also reachable directly,
    # bypassing that selection step entirely, from the /agent/tool
    # pipeline endpoint (see app.api.routes.run_selected_tools). Checked
    # unconditionally (not gated behind allow_disabled): allow_disabled
    # only ever means "bypass the enabled flag", never "bypass who/where
    # this tool may run".
    if not tool_def.is_allowed_for(state.user_role, state.session_mode):
        raise PermissionError(
            f"Tool '{tool_name}' is not allowed for role='{state.user_role}' "
            f"mode='{state.session_mode}'"
        )

    validate_tool_arguments(tool_def, tool_arguments)

    # Get the executor function for this tool
    # For now, this is a placeholder that we'll fill in with actual implementations
    executor = get_tool_executor(tool_name)

    if executor is None:
        raise NotImplementedError(f"Tool executor for '{tool_name}' not implemented")

    # Execute the tool
    try:
        result = executor(state, **tool_arguments)
        return {
            "success": True,
            "output": result,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
        return {
            "success": False,
            "output": None,
            "error": str(e),
        }


def validate_tool_arguments(tool_def: ToolDefinition, args: dict) -> None:

    for param in tool_def.parameters:
        if param.required:
            if param.name not in args:
                raise ValueError(
                    f"Missing required parameter '{param.name}' for tool '{tool_def.name}'"
                )

            value = args[param.name]
            if value is None:
                raise ValueError(f"Parameter '{param.name}' cannot be null")

            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Parameter '{param.name}' cannot be empty")


def get_tool_executor(tool_name: str) -> Callable | None:
    """
    Get the executor function for a tool.

    This dispatcher maps tool names to their implementation functions.
    """
    from app.tools.executors import get_tool_executor as get_domain_executor

    return get_domain_executor(tool_name)


def tool_executor_node(state: AgentState) -> Command:
    """
    Acting half of the ReAct loop: executes the single tool the reasoner
    just selected (state.cognitive.selected_tool / tool_arguments), records
    an Observation on the scratchpad, and routes back to react_reasoner so
    it can decide the next Thought/Action with that observation in hand.

    Confirmation-requiring tools pause here and route to WAIT_USER_INPUT;
    when the user confirms, the waiting node resumes here to actually run
    the tool.
    """
    tool_name = state.cognitive.selected_tool
    tool_arguments = state.cognitive.tool_arguments or {}
    thought = state.cognitive.pending_thought

    if not tool_name:
        logger.warning("tool_executor reached with no pending action")
        return Command(update=state, goto="generate_output_message")

    logger.info(
        f"Executing action [step {len(state.cognitive.scratchpad) + 1}]: "
        f"{tool_name} with args: {tool_arguments}"
    )

    # Try to fill in a parent id (problem_id / proposal_id) that the user
    # referred to by name rather than by literal ID, using whatever
    # get_context_ids already resolved earlier this turn.
    tool_arguments = _resolve_referenced_id(state, tool_name, tool_arguments)
    state.cognitive.tool_arguments = tool_arguments

    # ---- Required-parameter check ----
    # Validate BEFORE asking for confirmation: confirming a recap that is
    # missing required data (and only failing afterwards) is confusing and
    # wastes a turn. If something required is still missing, ask for it
    # directly instead of entering the confirmation flow.
    registry = get_tool_registry()
    tool_def = registry.get_tool(tool_name)
    if tool_def:
        missing = _missing_required_params(tool_def, tool_arguments)
        if missing:
            logger.info(f"'{tool_name}' missing required params: {missing}")
            state.cognitive.tool_confirmed = False
            state.cognitive.tool_confirmation_needed = False
            readable = ", ".join(missing)
            state.cognitive.messages_to_include = [
                f"To proceed I still need the following: {readable}. Could you provide it?"
            ]
            return Command(update=state, goto="generate_output_message")

    # ---- Tier-access consent gate ----
    # Distinct from the data-confirmation gate below: this asks permission
    # to use a *capability* at all (e.g. the exploitative tier's unguarded
    # free-form answers), not to confirm specific data. Derived from the
    # SELECTED TOOL's own agent_tier (see ToolDefinition.agent_tier) —
    # any tool tagged with a tier in TIERS_REQUIRING_CONSENT is gated,
    # there is no separate per-tool opt-in needed. Checked first —
    # deciding whether a capability may be used at all is logically prior
    # to confirming what gets submitted with it — and persists across
    # turns via CognitiveState.tier_consent, so unlike the gate below it
    # does not need a one-shot "confirmed" flag: granting consent updates
    # state directly, and re-entering this node re-checks
    # has_valid_tier_consent, which now simply passes.
    required_tier = tool_def.agent_tier if tool_def else None
    if required_tier not in TIERS_REQUIRING_CONSENT:
        required_tier = None
    if required_tier and not state.cognitive.has_valid_tier_consent(required_tier):
        logger.info(f"Pausing '{tool_name}' for tier-access consent ({required_tier})")
        return request_tier_consent(state, required_tier, resume_goto="tool_executor")

    # ---- Confirmation gate ----
    # Creation/edit/delete tools must never run silently: the first time we
    # reach one of them, stop and ask the user to confirm a recap of the
    # data that is about to be submitted. Only proceed once the user has
    # explicitly confirmed (tool_confirmed is set by WAIT_USER_INPUT after a
    # "yes").
    if tool_name in CONFIRMATION_REQUIRED_TOOLS and not state.cognitive.tool_confirmed:
        logger.info(f"Pausing '{tool_name}' for user confirmation")
        state.cognitive.tool_confirmation_needed = True
        return Command(update=state, goto="WAIT_USER_INPUT")

    # Confirmation (if it was required) has been consumed for this step.
    state.cognitive.tool_confirmed = False
    state.cognitive.tool_confirmation_needed = False

    # Both gates passed (or didn't apply) — the tool is actually about to
    # run, so this is the point where its declared tier takes effect for
    # the rest of the turn's response.
    _bump_active_agent(state, tool_def)

    publish_action(state.session_id, tool_name)

    try:
        result = execute_selected_tool(tool_name, tool_arguments, state)

        state.cognitive.tool_result = result

        # ---- Persist result in tool_results dict (long-term memory) ----
        # Use a unique key: tool_name, or tool_name__N if already present.
        result_key = tool_name
        collision = 0
        while result_key in state.cognitive.tool_results:
            collision += 1
            result_key = f"{tool_name}__{collision}"
        state.cognitive.tool_results[result_key] = result
        _trim_tool_results(state)

        # ---- Record the Observation on this turn's scratchpad ----
        state.cognitive.scratchpad.append(
            ReActStep(
                thought=thought,
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                observation=result,
                observation_key=result_key,
            )
        )

        # Store a reference (result_key) + a cheap status flag only — NOT
        # the full result again. The full result already lives in
        # state.cognitive.tool_results[result_key] (bounded by
        # MAX_STORED_TOOL_RESULTS / _trim_tool_results). Duplicating it
        # here defeated that cap: TraceBuffer keeps up to 1000 steps with
        # no per-entry size limit, and nothing ever reads step.data.result
        # back (grep confirms it — trace is write-only, consulted only via
        # AgentState.last_node and dump_to_file). That made every tool
        # result live in memory (and get independently re-serialized by
        # dump_to_file) twice for as long as the trace step survived,
        # regardless of the tool_results cap.
        state.add_trace(
            "tool_execution",
            tool_name,
            {"result_key": result_key, "success": result.get("success")},
        )

        logger.info(f"Tool '{tool_name}' result stored as '{result_key}'")

        if not result["success"]:
            state.cognitive.error_details = result.get("error", "Unknown error")
            return Command(update=state, goto="error")

        tool_output = (
            result.get("output", {}) if isinstance(result.get("output"), dict) else {}
        )
        assistant_actions = tool_output.get("assistant_action_data")
        if assistant_actions:
            existing = state.assistant_action_data or []
            if isinstance(assistant_actions, list):
                state.assistant_action_data = existing + assistant_actions
            else:
                state.assistant_action_data = existing + [assistant_actions]

        # The object this tool just edited/deleted may still be cached from
        # an earlier get_context_details — evict it so any later lookup
        # re-fetches fresh data instead of serving the stale copy.
        invalidation = _CACHE_INVALIDATION_MAP.get(tool_name)
        if invalidation:
            param_name, kind = invalidation
            obj_id = tool_arguments.get(param_name)
            if obj_id:
                state.cognitive.invalidate_cached_object(kind, obj_id)

        # Clear the pending-action slot now that it has been executed, then
        # hand back to the reasoner for the next Thought/Action decision.
        state.cognitive.selected_tool = None
        state.cognitive.tool_arguments = {}
        state.cognitive.pending_thought = ""
        return Command(update=state, goto="react_reasoner")

    except Exception as e:
        logger.error(f"Exception in tool executor: {e}", exc_info=True)
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")
