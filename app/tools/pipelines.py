"""Explicit, ordered tool pipelines that run OUTSIDE the ReAct loop.

Today these back the stateless ``POST /agent/tool`` endpoint
(app.api.routes.run_selected_tools) and, for the "summary" pipeline, the save
of a temporary scenario (app.tools.executors.scenario.execute_create_new_scenario),
so both produce the scenario summary through the exact same steps.

A pipeline runs against a throwaway ``AgentState`` with ``session_mode="system"``
(see new_system_state): it never reads or writes the caller's own state, so the
context cache / generation pipeline of the chat session are left untouched.
"""

import logging
from typing import Any, Dict, List, Mapping, Sequence

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# key -> ordered steps. Each step runs against the SAME throwaway state, so a
# later step sees the earlier ones' results exactly like inside a ReAct turn.
SUMMARY_STEPS: Sequence[Dict[str, Any]] = (
    {"tool_name": "get_context_details", "arguments": {}},
    {"tool_name": "summary_generation", "arguments": {}},
)
# report_generation fetches exactly what its kind of report needs (an empty
# context means "the whole territory"), so there is no get_context_details step
# before it: that would fetch evaluations for every entity, which only the
# detailed scenario report uses.
PDF_REPORT_STEPS: Sequence[Dict[str, Any]] = (
    {"tool_name": "report_generation", "arguments": {}},
)
PIPELINE_STEPS: Mapping[str, Sequence[Dict[str, Any]]] = {
    "summary": SUMMARY_STEPS,
    "pdf-report": PDF_REPORT_STEPS,
}


def new_system_state(
    *,
    territory: str,
    allowed_territories: List[str],
    user_id: str | None,
    user_role: str,
    current_context: Dict[str, Any],
) -> AgentState:
    """Throwaway, session-less state for a "system" pipeline. Never saved."""
    state = AgentState(
        allowed_territories=list(allowed_territories),
        territory=territory,
        user_id=f"{user_id or 'anonymous'}-system",
        user_role=user_role,
        # Pipeline tools (summary_generation, report_generation) declare
        # allowed_modes={"system"}, so they are reachable only from here.
        session_mode="system",
    )
    state.cognitive.current_context = current_context
    return state


def run_pipeline_steps(
    steps: Sequence[Dict[str, Any]], state: AgentState
) -> List[Dict[str, Any]]:
    """Run `steps` in order against `state`, stopping at the first failure.

    Returns one dict per executed step: {"tool_name", "success", "output",
    "error"}. summary_generation / report_generation are disabled in the
    registry (enabled=False) so they never show up in the chat's tool
    allowlist; allow_disabled=True bypasses only that flag — the role/mode
    checks in execute_selected_tool still apply (and pass for "system").
    """
    from app.agent.nodes.tool_executor import execute_selected_tool
    from app.tools.tool_registry import _ensure_tool_registry

    _ensure_tool_registry()

    results: List[Dict[str, Any]] = []
    for step in steps:
        outcome = execute_selected_tool(
            step["tool_name"], step["arguments"], state, allow_disabled=True
        )
        results.append({"tool_name": step["tool_name"], **outcome})
        if not outcome["success"]:
            logger.warning(
                f"Pipeline stopped at '{step['tool_name']}': {outcome['error']}"
            )
            break
    return results


def generate_temp_scenario_summary(
    state: AgentState, creation_session: str, evaluation_id: str
) -> str:
    """Summary text of a temporary (not yet saved) scenario.

    Equivalent to POST /agent/tool with key="summary" and
    current_context={"temp": {"creation_session": ..., "evaluation_id": ...}}
    (get_context_details -> summary_generation), run in-process against a
    throwaway state seeded from the chat session's territory / user / role.

    Raises RuntimeError if any step fails or the summary comes back empty, so
    the caller never saves a scenario with a missing summary by accident.
    """
    system_state = new_system_state(
        territory=state.territory,
        allowed_territories=state.allowed_territories,
        user_id=state.user_id,
        user_role=state.user_role,
        current_context={
            "temp": {
                "creation_session": creation_session,
                "evaluation_id": evaluation_id,
            }
        },
    )

    results = run_pipeline_steps(SUMMARY_STEPS, system_state)
    last = results[-1]
    if not last["success"]:
        raise RuntimeError(
            f"Could not generate the scenario summary ('{last['tool_name']}' "
            f"failed: {last['error']})"
        )

    message = (last["output"] or {}).get("message")
    if not isinstance(message, str) or not message.strip():
        raise RuntimeError("Could not generate the scenario summary (empty result)")
    return message
