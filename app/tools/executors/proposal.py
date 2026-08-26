"""Proposal tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def execute_list_available_proposals(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_proposals tool."""
    from app.tools.executor_backend_tools import get_all_proposals

    logger.info("Executing list_available_proposals tool")
    result = get_all_proposals.invoke({"tenant": state.tenant})

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

    from app.tools.executor_backend_tools import create_new_proposal

    result = create_new_proposal.invoke(
        {
            "tenant": state.tenant,
            "name": name,
            "problem_id": problem_id,
            "description": description,
            "resources": resources,
            "context": context,
            "impact": impact,
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

    from app.tools.executor_backend_tools import edit_proposal

    result = edit_proposal.invoke(
        {
            "tenant": state.tenant,
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


def execute_delete_proposal(
    state: AgentState,
    proposal_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.executor_backend_tools import delete_proposal

    result = delete_proposal.invoke(
        {"proposal_id": proposal_id, "tenant": state.tenant}
    )

    return result


EXECUTORS = {
    "list_available_proposals": execute_list_available_proposals,
    "create_new_proposal": execute_create_new_proposal,
    "edit_proposal": execute_edit_proposal,
    "delete_proposal": execute_delete_proposal,
}
