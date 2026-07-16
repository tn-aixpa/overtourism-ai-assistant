"""
Tool execution node for the agentic system.

Executes the LLM-selected tool and handles its results.
This node handles the actual tool invocation and error handling.
"""

import logging
from typing import Any, Dict, Callable
from langgraph.types import Command

from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.tool_schema import ToolDefinition
from app.prompts.entity_parsing import get_relatet_context_ids

logger = logging.getLogger(__name__)

_NOT_IMPLEMENTED_MSG = (
    "This feature is not yet available. "
    "The ability to {action} is planned for a future release. "
    "Please check back later or contact your system administrator."
)

# Hard cap on how many tool results we keep in memory per session. This is a
# second line of defense on top of the prompt-side truncation in
# build_prior_results_block: without it, state.cognitive.tool_results grows
# forever for the lifetime of a session (it's kept intentionally across
# turns so the tool_selector can see what already ran), which bloats both
# the in-memory AgentState and the JSON dumped to logs/state_<id>.json.
MAX_STORED_TOOL_RESULTS = 30

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
# an ID once get_context_ids has run earlier in the same plan. Covers both
# "parent" references (e.g. a new proposal's problem_id) and "target"
# references (e.g. the problem_id of the problem being edited/deleted) —
# resolution logic is identical in both cases: only fill in when exactly
# one candidate exists in current_context, otherwise leave it for the
# missing-parameter check to catch.
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


def execute_selected_tool(
    tool_name: str,
    tool_arguments: Dict[str, Any],
    state: AgentState,
) -> Dict[str, Any]:
    """
    Execute a tool with the given arguments.

    Handles dispatching to tool-specific implementations.
    Returns the tool result.
    """
    logger.info(f"Executing tool: {tool_name} with args: {tool_arguments}")

    # Get the tool definition
    registry = get_tool_registry()
    tool_def = registry.get_tool(tool_name)

    if not tool_def:
        raise ValueError(f"Tool '{tool_name}' not found in registry")

    if not tool_def.enabled:
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
    # Map tool names to executor functions
    executors: Dict[str, Callable] = {
        # System
        "get_system_capabilities": execute_get_system_capabilities,
        # Data retrieval
        "list_available_problems": execute_list_available_problems,
        "list_available_proposals": execute_list_available_proposals,
        "list_available_scenarios": execute_list_available_scenarios,
        "get_context_ids": execute_get_context_ids,
        "get_context_details": execute_get_context_details,
        # Interaction
        "interact_with_context": execute_interact_with_context,
        # Creation stubs
        "create_new_problem": execute_create_new_problem,
        "create_new_proposal": execute_create_new_proposal,
        "create_new_scenario": execute_create_new_scenario,  # not yet implemented
        # Editing stubs
        "edit_problem": execute_edit_problem,
        "edit_proposal": execute_edit_proposal,
        "edit_scenario": execute_edit_scenario,  # not yet implemented
        # Deletion stubs
        "delete_problem": execute_delete_problem,
        "delete_proposal": execute_delete_proposal,
        "delete_scenario": execute_delete_scenario,
        # Utility
        "lookup_glossary": execute_lookup_glossary,
    }

    return executors.get(tool_name)


def _trim_tool_results(state: AgentState) -> None:
    """Evict the oldest tool_results entries once we're over the cap.

    Never evicts a key produced by the plan currently executing —
    generate_output_message_node needs those to build the final answer.
    """
    results = state.cognitive.tool_results
    protected = set(state.cognitive.current_plan_result_keys)

    while len(results) > MAX_STORED_TOOL_RESULTS:
        for key in results:  # dicts preserve insertion order -> oldest first
            if key not in protected:
                del results[key]
                break
        else:
            # Everything remaining belongs to the current plan; stop rather
            # than evict something generate_output_message_node still needs.
            break


def tool_executor_node(state: AgentState) -> Command:
    """
    Main tool executor node that iterates through the tool plan.

    On each graph visit it executes the *current* tool (tool_plan[tool_plan_index]),
    stores the result in cognitive.tool_results, advances the index, and either:
      - loops back to itself (via tool_executor) for the next tool in the plan, or
      - forwards to generate_output_message when the plan is exhausted.

    Confirmation-requiring tools still pause the plan and route to WAIT_USER_INPUT;
    when the user confirms, the waiting node resumes here.
    """
    plan = state.cognitive.tool_plan
    idx = state.cognitive.tool_plan_index

    if not plan or idx >= len(plan):
        logger.warning("tool_executor reached with empty/exhausted plan")
        return Command(update=state, goto="generate_output_message")

    current_step = plan[idx]
    tool_name = current_step["tool_name"]
    tool_arguments = current_step.get("arguments", {})

    logger.info(
        f"Executing tool [{idx + 1}/{len(plan)}]: {tool_name} with args: {tool_arguments}"
    )

    # Try to fill in a parent id (problem_id / proposal_id) that the user
    # referred to by name rather than by literal ID, using whatever
    # get_context_ids already resolved earlier in this plan.
    tool_arguments = _resolve_referenced_id(state, tool_name, tool_arguments)

    # Keep legacy aliases in sync so existing executors that read
    # state.cognitive.selected_tool / tool_arguments continue to work.
    state.cognitive.selected_tool = tool_name
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

    # ---- Confirmation gate ----
    # Creation tools must never run silently: the first time we reach one of
    # them, stop and ask the user to confirm a recap of the data that is
    # about to be submitted. Only proceed once the user has explicitly
    # confirmed (tool_confirmed is set by WAIT_USER_INPUT after a "yes").
    if tool_name in CONFIRMATION_REQUIRED_TOOLS and not state.cognitive.tool_confirmed:
        logger.info(f"Pausing '{tool_name}' for user confirmation")
        state.cognitive.tool_confirmation_needed = True
        return Command(update=state, goto="WAIT_USER_INPUT")

    # Confirmation (if it was required) has been consumed for this step.
    state.cognitive.tool_confirmed = False
    state.cognitive.tool_confirmation_needed = False

    try:
        result = execute_selected_tool(tool_name, tool_arguments, state)

        state.cognitive.tool_result = result

        # ---- Persist result in tool_results dict ----
        # Use a unique key: tool_name, or tool_name__N if already present.
        result_key = tool_name
        collision = 0
        while result_key in state.cognitive.tool_results:
            collision += 1
            result_key = f"{tool_name}__{collision}"
        state.cognitive.tool_results[result_key] = result
        state.cognitive.current_plan_result_keys.append(result_key)
        _trim_tool_results(state)

        state.add_trace(
            "tool_execution",
            tool_name,
            {"plan_index": idx, "result_key": result_key, "result": result},
        )

        logger.info(f"Tool '{tool_name}' result stored as '{result_key}'")

        if not result["success"]:
            state.cognitive.error_details = result.get("error", "Unknown error")
            return Command(update=state, goto="error")

        # Confirmation pause: halt the plan here until the user responds.
        if state.cognitive.tool_confirmation_needed:
            # tool_plan_index is NOT advanced — after confirmation the waiting
            # node will route back here and we will advance then.
            return Command(update=state, goto="WAIT_USER_INPUT")

        # Advance to next tool
        state.cognitive.tool_plan_index = idx + 1

        # More tools in the plan?
        if state.cognitive.tool_plan_index < len(plan):
            next_tool = plan[state.cognitive.tool_plan_index]["tool_name"]
            logger.info(f"Continuing to next tool in plan: {next_tool}")
            return Command(update=state, goto="tool_executor")

        # Plan exhausted — generate final response.
        return Command(update=state, goto="generate_output_message")

    except Exception as e:
        logger.error(f"Exception in tool executor: {e}", exc_info=True)
        state.cognitive.error_details = str(e)
        return Command(update=state, goto="error")


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================


def execute_get_system_capabilities(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute get_system_capabilities tool."""
    from app.config import SYSTEM_DESCRIPTION

    logger.info("Executing get_system_capabilities tool")

    return {
        "success": True,
        "system_description": SYSTEM_DESCRIPTION,
    }


def execute_list_available_problems(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_problems tool."""
    from app.tools.backend_tools import get_all_problems

    logger.info("Executing list_available_problems tool")
    result = get_all_problems.invoke({})

    return result


def execute_list_available_proposals(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_proposals tool."""
    from app.tools.backend_tools import get_all_proposals

    logger.info("Executing list_available_proposals tool")
    result = get_all_proposals.invoke({})

    return result


def execute_list_available_scenarios(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_scenarios tool."""
    from app.tools.backend_tools import get_all_scenarios

    logger.info("Executing list_available_scenarios tool")
    result = get_all_scenarios.invoke({})

    return result


def execute_get_context_ids(
    state: AgentState,
    user_intent: str,
    source_tools: list,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute get_context_ids tool.

    Reads raw list data that was already collected by list_available_problems /
    list_available_proposals / list_available_scenarios (stored in
    state.cognitive.tool_results) and uses an LLM call to reason over every
    field of every object, returning only the IDs that match the user's intent.

    Returns:
        {
            "success": True,
            "context_ids": {
                "problems":  [<id>, ...],
                "proposals": [<id>, ...],
                "scenarios": [<id>, ...],
            }
        }
    """
    import json
    import re

    logger.info(
        f"Executing get_context_ids | intent='{user_intent}' | sources={source_tools}"
    )

    # ------------------------------------------------------------------ #
    # 3. Call the LLM and parse
    # ------------------------------------------------------------------ #
    try:
        raw = get_relatet_context_ids(state, user_intent, source_tools)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        context_ids = json.loads(raw)

        # Ensure all three keys exist and are lists
        for key in ("problems", "proposals", "scenarios"):
            if key not in context_ids or not isinstance(context_ids[key], list):
                context_ids[key] = []

    except Exception as e:
        logger.exception("get_context_ids: failed to parse LLM response")
        return {
            "success": False,
            "error": str(e),
            "context_ids": {"problems": [], "proposals": [], "scenarios": []},
        }

    logger.info(f"get_context_ids resolved: {context_ids}")

    state.cognitive.current_context = context_ids
    return {
        "success": True,
        "context_ids": context_ids,
    }


def execute_get_context_details(
    state: AgentState,
) -> Dict[str, Any]:
    """Execute get_context_details tool."""
    from app.tools.backend_tools import get_data_from_context

    logger.info(
        f"Executing get_context_details for context {state.cognitive.current_context}"
    )

    retrieved_context = get_data_from_context.invoke(
        {"current_context": state.cognitive.current_context}
    )

    state.cognitive.retrieved_context = retrieved_context

    return retrieved_context


def execute_interact_with_context(
    state: AgentState, query: str, **kwargs
) -> Dict[str, Any]:
    """Execute interact_with_context tool."""
    import json
    from app.utils.llm import llm_interaction

    logger.info(f"Executing interact_with_context tool with query: {query}")

    retrieved = state.cognitive.retrieved_context
    if not retrieved:
        raise ValueError("No context data available — run get_context_details first")

    prompt = f"""You are an analyst for a tourism digital twin platform.
Answer the following question using ONLY the data provided below.
If the data does not contain enough information to answer, say so explicitly — do not infer or speculate.
Be concise and factual. Use a neutral, professional tone.

Question: {query}

Context data:
{json.dumps(retrieved, indent=2, default=str)}

Answer:"""

    answer = llm_interaction(state, prompt)

    return {
        "success": True,
        "message": answer,  # ← "message" key is now always present
    }


# =============================================================================
# CREATION STUBS
# =============================================================================


def execute_create_new_problem(
    state: AgentState,
    name: str,
    description: str,
    objectives: str | None = None,
    additional_data: str | None = None,
) -> Dict[str, Any]:

    from app.tools.backend_tools import create_new_problem

    result = create_new_problem.invoke(
        {
            "name": name,
            "description": description,
            "objectives": objectives,
            "additional_data": additional_data,
        }
    )

    return result


def execute_create_new_proposal(
    state: AgentState,
    name: str = "",
    problem_id: str = "",
    description: str = "",
    resources: str = "",
    context: str = "",
    impact: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import create_new_proposal

    result = create_new_proposal.invoke(
        {
            "name": name,
            "problem_id": problem_id,
            "description": description,
            "resources": resources,
            "context": context,
            "impact": impact,
        }
    )

    return result


def execute_create_new_scenario(
    state: AgentState,
    name: str = "",
    proposal_id: str = "",
    description: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Stub executor for create_new_scenario — feature not yet implemented."""
    logger.info(f"create_new_scenario called (not implemented) | name='{name}'")
    return {
        "success": True,
        "not_implemented": True,
        "message": _NOT_IMPLEMENTED_MSG.format(action="create new scenarios"),
        "received": {
            "name": name,
            "proposal_id": proposal_id,
            "description": description,
        },
    }


# =============================================================================
# EDIT STUBS
# =============================================================================


def execute_edit_problem(
    state: AgentState,
    problem_id: str = "",
    name: str = "",
    description: str = "",
    objectives: str | None = None,
    additional_data: str | None = None,
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import edit_problem

    result = edit_problem.invoke(
        {
            "problem_id": problem_id,
            "name": name,
            "description": description,
            "objectives": objectives,
            "additional_data": additional_data,
        }
    )

    return result


def execute_edit_proposal(
    state: AgentState,
    proposal_id: str = "",
    name: str = "",
    problem_id: str = "",
    description: str = "",
    resources: str = "",
    context: str = "",
    impact: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import edit_proposal

    result = edit_proposal.invoke(
        {
            "proposal_id": proposal_id,
            "name": name,
            "problem_id": problem_id,
            "description": description,
            "resources": resources,
            "context": context,
            "impact": impact,
        }
    )

    return result


def execute_edit_scenario(
    state: AgentState,
    name: str = "",
    proposal_id: str = "",
    description: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Stub executor for edit_scenario — feature not yet implemented."""
    logger.info(f"edit_scenario called (not implemented) | name='{name}'")
    return {
        "success": True,
        "not_implemented": True,
        "message": _NOT_IMPLEMENTED_MSG.format(action="create new scenarios"),
        "received": {
            "name": name,
            "proposal_id": proposal_id,
            "description": description,
        },
    }


# =============================================================================
# DELETE STUBS
# =============================================================================


def execute_delete_problem(
    state: AgentState,
    problem_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import delete_problem

    result = delete_problem.invoke({"problem_id": problem_id})

    return result


def execute_delete_proposal(
    state: AgentState,
    proposal_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import delete_proposal

    result = delete_proposal.invoke({"proposal_id": proposal_id})

    return result


def execute_delete_scenario(
    state: AgentState,
    scenario_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.backend_tools import delete_scenario

    result = delete_scenario.invoke({"scenario_id": scenario_id})

    return result


# =============================================================================
# GLOSSARY LOOKUP
# =============================================================================


def execute_lookup_glossary(
    state: AgentState,
    query: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute lookup_glossary tool.

    Performs a case-insensitive fuzzy search over the GLOSSARY dict in config.
    Matches the query tokens against: term name, aliases, and related_terms.
    Returns all matching entries with their full detail.
    """
    from app.config import GLOSSARY

    logger.info(f"Executing lookup_glossary | query='{query}'")

    tokens = [t.strip().lower() for t in query.split() if t.strip()]
    if not tokens:
        return {
            "success": False,
            "error": "Empty query — please provide at least one search term.",
            "matches": [],
        }

    matches = {}
    for term, entry in GLOSSARY.items():
        # Build a flat list of strings to match against
        searchable = [term] + entry.get("aliases", []) + entry.get("related_terms", [])
        searchable_lower = " ".join(s.lower() for s in searchable)

        if any(tok in searchable_lower for tok in tokens):
            matches[term] = entry

    if not matches:
        return {
            "success": True,
            "message": (
                f"No glossary entries found for '{query}'. "
                "Try broader keywords or ask about a specific platform concept."
            ),
            "matches": [],
        }

    # Format for readability in the output generator
    formatted = []
    for term, entry in matches.items():
        formatted.append(
            {
                "term": term,
                "definition": entry["definition"],
                "aliases": entry.get("aliases", []),
                "related_terms": entry.get("related_terms", []),
                "examples": entry.get("examples", []),
            }
        )

    logger.info(f"lookup_glossary found {len(formatted)} match(es) for '{query}'")

    return {
        "success": True,
        "query": query,
        "matches": formatted,
    }
