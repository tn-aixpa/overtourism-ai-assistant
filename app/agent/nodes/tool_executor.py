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

logger = logging.getLogger(__name__)


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
    
    # Get the executor function for this tool
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


def get_tool_executor(tool_name: str) -> Callable | None:
    """
    Get the executor function for a tool.
    
    This dispatcher maps tool names to their implementation functions.
    """
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
    }
    
    return executors.get(tool_name)


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def execute_get_system_capabilities(
    state: AgentState,
    **kwargs
) -> Dict[str, Any]:
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

    Reads raw list data already collected by the list_available_* tools
    (stored in state.cognitive.tool_results) and uses an LLM call to reason
    over every field of every object, returning only the IDs relevant to the
    user's intent.

    Cross-entity relationships are handled automatically:
      - The current_context (IDs already resolved in this turn) is injected
        into the prompt so the LLM can follow relationship fields
        (e.g. a proposal's `problem_ids` field) even when those IDs were
        resolved from a *different* list tool.
      - When source_tools includes multiple entity types the LLM can therefore
        answer questions like "proposals for problem X" without requiring a
        separate tool call.

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
    from app.utils.llm import llm_interaction

    logger.info(
        f"Executing get_context_ids | intent='{user_intent}' | sources={source_tools}"
    )

    # ------------------------------------------------------------------ #
    # 1. Collect the raw list data from tool_results
    # ------------------------------------------------------------------ #
    tool_results = state.cognitive.tool_results

    def _find_result(key_prefix: str) -> Any:
        """Return the first tool_results value whose key starts with key_prefix."""
        for k, v in tool_results.items():
            if k == key_prefix or k.startswith(key_prefix + "__"):
                return v
        return None

    sections: Dict[str, Any] = {}
    for source in source_tools:
        data = _find_result(source)
        if data is None:
            logger.warning(
                f"get_context_ids: source '{source}' not found in tool_results "
                f"(available keys: {list(tool_results.keys())})"
            )
        else:
            sections[source] = data

    if not sections:
        return {
            "success": False,
            "error": (
                "None of the requested source tools have results in tool_results. "
                f"Requested: {source_tools}. "
                f"Available: {list(tool_results.keys())}. "
                "Run the list tools first."
            ),
            "context_ids": {"problems": [], "proposals": [], "scenarios": []},
        }

    # ------------------------------------------------------------------ #
    # 2. Build the prior-context block
    #    Inject any IDs already resolved in this conversation turn so the
    #    LLM can follow cross-entity relationship fields.
    # ------------------------------------------------------------------ #
    prior_context = state.cognitive.current_context
    prior_context_block = ""
    has_prior = any(
        prior_context.get(k) for k in ("problems", "proposals", "scenarios")
    )
    if has_prior:
        prior_context_block = f"""
Previously resolved context IDs (from this conversation turn):
{json.dumps(prior_context, indent=2)}

Use these IDs to follow relationship fields in the data below
(e.g. if a proposal has a `problem_ids` field that contains one of the
resolved problem IDs, that proposal is relevant to the current context).
"""

    # ------------------------------------------------------------------ #
    # 3. Build prompt
    # ------------------------------------------------------------------ #
    sections_block = json.dumps(sections, indent=2, default=str)

    prompt = f"""
You are a semantic matching assistant for a digital twin platform about tourism management.

Your task: given a user intent and a set of object lists fetched from the backend,
identify which objects (by their ID) are relevant to the intent.

Consider ALL fields of each object (name, description, tags, location, relationships,
foreign-key arrays such as `problem_ids`, `proposal_ids`, `scenario_ids`, etc.)
when deciding relevance.

CROSS-ENTITY RELATIONSHIPS: If the user is asking about entities related to
previously resolved ones (e.g. "proposals for these problems"), use the
relationship fields in the data to find matching IDs even when those fields
belong to a different entity type than the one being asked about.
Be inclusive — if an object is plausibly related, include it.
{prior_context_block}
User intent:
\"{user_intent}\"

Available data (raw API responses, one section per list tool):
{sections_block}

Return ONLY a valid JSON object with exactly these three keys (lists may be empty):
{{
  "problems":  ["<id>", ...],
  "proposals": ["<id>", ...],
  "scenarios": ["<id>", ...]
}}

Do not include any explanation or markdown. Return JSON only.
"""

    # ------------------------------------------------------------------ #
    # 4. Call the LLM and parse
    # ------------------------------------------------------------------ #
    try:
        raw = llm_interaction(state, prompt).strip()
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

    # Merge with prior context rather than replacing it entirely, so that
    # IDs resolved in a previous step of the same plan are not lost.
    merged: Dict[str, list] = {}
    for key in ("problems", "proposals", "scenarios"):
        existing = prior_context.get(key, [])
        new_ids = context_ids.get(key, [])
        # Union, preserving order (existing first)
        merged[key] = existing + [i for i in new_ids if i not in existing]

    state.cognitive.current_context = merged
    return {
        "success": True,
        "context_ids": merged,
    }


def execute_get_context_details(
    state: AgentState,
) -> Dict[str, Any]:
    """Execute get_context_details tool."""
    from app.tools.backend_tools import get_data_from_context
    
    logger.info(f"Executing get_context_details for context {state.cognitive.current_context}")

    retrieved_context = get_data_from_context.invoke({
        "current_context": state.cognitive.current_context
    })
    
    state.cognitive.retrieved_context = retrieved_context
       
    return retrieved_context

def execute_interact_with_context(
    state: AgentState,
    query: str,
    **kwargs
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
        "message": answer,
    }


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

    logger.info(f"Executing tool [{idx + 1}/{len(plan)}]: {tool_name} with args: {tool_arguments}")

    # Keep legacy aliases in sync so existing executors that read
    # state.cognitive.selected_tool / tool_arguments continue to work.
    state.cognitive.selected_tool = tool_name
    state.cognitive.tool_arguments = tool_arguments

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