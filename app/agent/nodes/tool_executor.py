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

from app.agent.state import AgentState, ReActStep
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
    # to use a *capability* at all (e.g. the exploitative tier's
    # unguarded strategy suggestions), not to confirm specific data.
    # Checked first — deciding whether a capability may be used at all is
    # logically prior to confirming what gets submitted with it — and
    # persists across turns via CognitiveState.tier_consent, so unlike the
    # gate below it does not need a one-shot "confirmed" flag: granting
    # consent updates state directly, and re-entering this node re-checks
    # has_valid_tier_consent, which now simply passes.
    required_tier = (
        getattr(tool_def, "requires_tier_consent", None) if tool_def else None
    )
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

        state.add_trace(
            "tool_execution",
            tool_name,
            {"result_key": result_key, "result": result},
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
