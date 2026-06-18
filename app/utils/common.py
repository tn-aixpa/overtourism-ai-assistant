from __future__ import annotations
# import re
import logging

from app.agent.state import AgentState
from app.utils.error_codes import GraphError

logger = logging.getLogger(__name__)

WORKFLOW_TO_INTENT = {
    AgentState.Workflow.PROBLEM_CREATION: "CREATE_NEW_PROBLEM",
    AgentState.Workflow.PROPOSAL_CREATION: "CREATE_NEW_PROPOSAL",
    AgentState.Workflow.SCENARIO_CREATION: "CREATE_NEW_SCENARIO",
    AgentState.Workflow.INTERACTION: "INTERACT_CONTEXT",
}

class RequestHandlingException(GraphError):
    """Exception raised when request handling fails."""
    def __init__(self, message: str):
        super().__init__(
            details=str(message)
        )