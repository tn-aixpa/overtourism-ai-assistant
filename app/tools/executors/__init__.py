"""Domain-grouped tool execution entry points."""

from typing import Any, Callable

from app.tools.executors.analysis import EXECUTORS as _analysis
from app.tools.executors.analysis_widgets import EXECUTORS as _analysis_widgets
from app.tools.executors.entities import EXECUTORS as _entities
from app.tools.executors.indexes import EXECUTORS as _indexes
from app.tools.executors.problem import EXECUTORS as _problem
from app.tools.executors.proposal import EXECUTORS as _proposal
from app.tools.executors.scenario import EXECUTORS as _scenario
from app.tools.executors.system_utility import EXECUTORS as _system_utility

EXECUTORS: dict[str, Callable[..., Any]] = {
    **_system_utility,
    **_analysis,
    **_analysis_widgets,
    **_entities,
    **_indexes,
    **_problem,
    **_proposal,
    **_scenario,
}


def get_tool_executor(tool_name: str) -> Callable[..., Any] | None:
    """Return the implementation registered for ``tool_name``."""
    return EXECUTORS.get(tool_name)


__all__ = ["EXECUTORS", "get_tool_executor"]
