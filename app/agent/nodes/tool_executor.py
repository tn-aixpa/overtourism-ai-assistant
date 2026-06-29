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
                raise ValueError(
                    f"Parameter '{param.name}' cannot be null"
                )

            if isinstance(value, str) and not value.strip():
                raise ValueError(
                    f"Parameter '{param.name}' cannot be empty"
                )

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

        # Creation stubs (not yet implemented)
        "create_new_problem": execute_create_new_problem,
        "create_new_proposal": execute_create_new_proposal,
        "create_new_scenario": execute_create_new_scenario,

        # Utility
        "lookup_glossary": execute_lookup_glossary,
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
    from app.utils.llm import llm_interaction

    logger.info(
        f"Executing get_context_ids | intent='{user_intent}' | sources={source_tools}"
    )

    # ------------------------------------------------------------------ #
    # 1. Collect the raw list data from tool_results
    # ------------------------------------------------------------------ #
    tool_results = state.cognitive.tool_results

    # Build a mapping  entity_type -> raw data, tolerating key variants
    # (e.g. the selector might store them as "list_available_problems" or
    #  with a collision suffix like "list_available_problems__1").
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
    # 2. Build prompt
    # ------------------------------------------------------------------ #
    sections_block = json.dumps(sections, indent=2, default=str)

    prompt = f"""
You are a semantic matching assistant for a digital twin platform about tourism management.

Your task: given a user intent and a set of object lists fetched from the backend,
identify which objects (by their ID) are relevant to the intent.

Consider ALL fields of each object (name, description, tags, location, relationships, etc.)
when deciding relevance. Be inclusive — if an object is plausibly related, include it.

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
    # 3. Call the LLM and parse
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
        "message": answer,   # ← "message" key is now always present
    }




# =============================================================================
# NOT-YET-IMPLEMENTED CREATION STUBS
# =============================================================================

_NOT_IMPLEMENTED_MSG = (
    "This feature is not yet available. "
    "The ability to {action} is planned for a future release. "
    "Please check back later or contact your system administrator."
)


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
    **kwargs,
) -> Dict[str, Any]:
    """Stub executor for create_new_proposal — feature not yet implemented."""
    logger.info(f"create_new_proposal called (not implemented) | name='{name}'")
    return {
        "success": True,
        "not_implemented": True,
        "message": _NOT_IMPLEMENTED_MSG.format(action="create new proposals"),
        "received": {"name": name, "problem_id": problem_id, "description": description},
    }


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
        "received": {"name": name, "proposal_id": proposal_id, "description": description},
    }


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
        searchable = (
            [term]
            + entry.get("aliases", [])
            + entry.get("related_terms", [])
        )
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
        formatted.append({
            "term": term,
            "definition": entry["definition"],
            "aliases": entry.get("aliases", []),
            "related_terms": entry.get("related_terms", []),
            "examples": entry.get("examples", []),
        })

    logger.info(f"lookup_glossary found {len(formatted)} match(es) for '{query}'")

    return {
        "success": True,
        "query": query,
        "matches": formatted,
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