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
from app.agent.events import publish

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
        "get_context_details": execute_get_context_details,
        
        # Context management
        "set_active_context": execute_set_active_context,
        
        # Problem management
        "extract_problem_details": execute_extract_problem_details,
        "create_problem": execute_create_problem,
        
        # Proposal management
        "extract_proposal_details": execute_extract_proposal_details,
        "create_proposal": execute_create_proposal,
        
        # Scenario management
        "extract_scenario_details": execute_extract_scenario_details,
        "create_scenario": execute_create_scenario,
        
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


def execute_get_context_details(
    state: AgentState,
    context_type: str,
    context_ids: list,
    extract_editable: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """Execute get_context_details tool."""
    from app.tools.backend_tools import get_data_from_context
    
    logger.info(f"Executing get_context_details for {context_type}s: {context_ids}")
       
    result = get_data_from_context.invoke({
        "context_type": context_type,
        "context": context_ids,
        "relations": {},
        "extract_editable": extract_editable,
    })
    
    # Store context data in state
    state.cognitive.context_data.update(result.get("retrieved", {}))
    if result.get("editable_indexes"):
        state.cognitive.editable_indexes = result["editable_indexes"]
    
    return result


def execute_set_active_context(
    state: AgentState,
    context_type: str,
    context_id: str,
    **kwargs
) -> Dict[str, Any]:
    """Execute set_active_context tool."""
    logger.info(f"Setting active context to {context_type}: {context_id}")
    
    
    available_ids = {}
    if context_id not in available_ids:
        raise ValueError(f"Context {context_type} '{context_id}' not found")
    
    # Update state
    state.cognitive.previous_context = state.cognitive.active_context
    state.cognitive.active_context_type = context_type
    state.cognitive.active_context = [context_id]
    
    return {
        "success": True,
        "message": f"Active context set to {context_type}: {context_id}",
        "previous_context": state.cognitive.previous_context,
    }


def execute_extract_problem_details(
    state: AgentState,
    user_input: str,
    **kwargs
) -> Dict[str, Any]:
    """Execute extract_problem_details tool."""
    from app.utils.llm_structured_extractions import extract_problem_data
    from app.utils.llm import parse_llm_json
    from app.utils.backend_integration_classes import (
        ProblemInfoSchema, ProblemInfo, build_schema_data
    )
    
    logger.info("Executing extract_problem_details tool")
    
    # Set user input for extraction
    state.user_input = user_input
    
    # Extract problem data using existing LLM logic
    answer = extract_problem_data(state)
    problem = parse_llm_json(answer)
    
    schema = ProblemInfoSchema.default()
    
    try:
        extracted = build_schema_data(schema, problem, ProblemInfo)
        state.cognitive.problem_info_extracted = extracted
        state.cognitive.extracted_all_problem = True
        
        # Mark as needing confirmation
        state.cognitive.tool_confirmation_needed = True
        state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        
        return {
            "success": True,
            "extracted": extracted,
            "needs_confirmation": True,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "needs_confirmation": False,
        }


def execute_create_problem(
    state: AgentState,
    problem_title: str,
    problem_description: str,
    objectives: list = None,
    available_subsystems: list = None,
    additional_data: dict = None,
    **kwargs
) -> Dict[str, Any]:
    """Execute create_problem tool."""
    from app.tools.backend_tools import create_problem_instance
    
    logger.info(f"Executing create_problem tool: {problem_title}")
    
    payload = {
        "problem_name": problem_title,
        "problem_description": problem_description,
        "objective": objectives or [],
        "groups": available_subsystems or [],
        "links": additional_data or {},
    }
    
    # Remove empty fields
    payload = {k: v for k, v in payload.items() if v not in [None, "", [], {}]}
    
    result = create_problem_instance.invoke({"payload": payload})
    
    # Update state
    state.active_workflow = None
    state.waiting_for = None
    state.cognitive.extracted_all_problem = False
    
    return result


def execute_extract_proposal_details(
    state: AgentState,
    user_input: str,
    **kwargs
) -> Dict[str, Any]:
    """Execute extract_proposal_details tool."""
    from app.utils.llm_structured_extractions import extract_proposal_data
    from app.utils.llm import parse_llm_json
    from app.utils.backend_integration_classes import (
        ProposalInfoSchema, ProposalInfo, build_schema_data
    )
    
    logger.info("Executing extract_proposal_details tool")
    
    # Check for active problem context
    if state.cognitive.active_context_type != "problem":
        raise ValueError("No active problem context. Please set a problem context first.")
    
    # Set user input for extraction
    state.user_input = user_input
    
    # Extract proposal data using existing LLM logic
    answer = extract_proposal_data(state)
    proposal = parse_llm_json(answer)
    
    schema = ProposalInfoSchema.default()
    
    try:
        extracted = build_schema_data(schema, proposal, ProposalInfo)
        state.cognitive.proposal_info_extracted = extracted
        state.cognitive.extracted_all_proposal = True
        
        # Mark as needing confirmation
        state.cognitive.tool_confirmation_needed = True
        state.waiting_for = AgentState.WaitingFor.PROPOSAL_CONFIRMATION
        
        return {
            "success": True,
            "extracted": extracted,
            "needs_confirmation": True,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "needs_confirmation": False,
        }


def execute_create_proposal(
    state: AgentState,
    proposal_title: str,
    proposal_description: str,
    connected_scenarios: list = None,
    additional_data: dict = None,
    **kwargs
) -> Dict[str, Any]:
    """Execute create_proposal tool."""
    from app.tools.backend_tools import create_proposal_instance
    
    logger.info(f"Executing create_proposal tool: {proposal_title}")
    
    # Check for active problem context
    if state.cognitive.active_context_type != "problem":
        raise ValueError("No active problem context")
    
    problem_id = state.cognitive.active_context[0]
    
    payload = {
        "proposal_title": proposal_title,
        "proposal_description": proposal_description,
        "additional_data": additional_data or {},
    }
    
    result = create_proposal_instance.invoke({
        "problem_id": problem_id,
        "payload": payload,
    })
    
    # Update state
    state.active_workflow = None
    state.waiting_for = None
    state.cognitive.extracted_all_proposal = False
    
    return result


def execute_extract_scenario_details(
    state: AgentState,
    user_input: str,
    **kwargs
) -> Dict[str, Any]:
    """Execute extract_scenario_details tool."""
    logger.info("Executing extract_scenario_details tool")
    
    # Check for active proposal context
    if state.cognitive.active_context_type != "proposal":
        raise ValueError("No active proposal context. Please set a proposal context first.")
    
    # TODO: Implement scenario extraction similar to problem/proposal
    # For now, return placeholder
    return {
        "success": True,
        "message": "Scenario extraction not yet implemented",
        "needs_confirmation": True,
    }


def execute_create_scenario(
    state: AgentState,
    scenario_name: str,
    scenario_description: str,
    model_values: dict,
    additional_data: dict = None,
    **kwargs
) -> Dict[str, Any]:
    """Execute create_scenario tool."""
    logger.info(f"Executing create_scenario tool: {scenario_name}")
    
    # Check for active proposal context
    if state.cognitive.active_context_type != "proposal":
        raise ValueError("No active proposal context")
    
    # TODO: Implement scenario creation
    # For now, return placeholder
    return {
        "success": True,
        "message": "Scenario creation not yet implemented",
    }


def execute_interact_with_context(
    state: AgentState,
    interaction_type: str,
    query: str = None,
    modifications: dict = None,
    **kwargs
) -> Dict[str, Any]:
    """Execute interact_with_context tool."""
    logger.info(f"Executing interact_with_context tool: {interaction_type}")
    
    if not state.cognitive.active_context_type:
        raise ValueError("No active context to interact with")
    
    # TODO: Implement different interaction types
    return {
        "success": True,
        "message": f"Interaction type '{interaction_type}' not yet implemented",
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
    publish(state.session_id, f"Executing: {tool_name}")

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
