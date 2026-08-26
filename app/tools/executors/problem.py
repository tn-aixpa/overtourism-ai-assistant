"""Problem tool implementations."""

from typing import Any, Dict
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def execute_list_available_problems(state: AgentState, **kwargs) -> Dict[str, Any]:
    """Execute list_available_problems tool."""
    from app.tools.executor_backend_tools import get_all_problems

    logger.info("Executing list_available_problems tool")
    result = get_all_problems.invoke({"tenant": state.tenant})

    return result


def execute_create_new_problem(
    state: AgentState,
    name: str,
    description: str,
    objective: str | None = None,
    additional_data: str | None = None,
) -> Dict[str, Any]:

    from app.tools.executor_backend_tools import create_new_problem

    result = create_new_problem.invoke(
        {
            "tenant": state.tenant,
            "name": name,
            "description": description,
            "objective": objective,
            "additional_data": additional_data,
        }
    )

    return result


def execute_edit_problem(
    state: AgentState,
    problem_id: str = "",
    name: str = "",
    description: str = "",
    objective: str | None = None,
    additional_data: str | None = None,
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.executor_backend_tools import edit_problem

    result = edit_problem.invoke(
        {
            "tenant": state.tenant,
            "problem_id": problem_id,
            "name": name,
            "description": description,
            "objective": objective,
            "additional_data": additional_data,
        }
    )

    return result


def execute_delete_problem(
    state: AgentState,
    problem_id: str = "",
    **kwargs,
) -> Dict[str, Any]:

    from app.tools.executor_backend_tools import delete_problem

    result = delete_problem.invoke({"problem_id": problem_id, "tenant": state.tenant})

    return result


EXECUTORS = {
    "list_available_problems": execute_list_available_problems,
    "create_new_problem": execute_create_new_problem,
    "edit_problem": execute_edit_problem,
    "delete_problem": execute_delete_problem,
}
