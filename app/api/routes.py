# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException
import logging

from app.schemas import AgentRequest, AgentResponse
from app.agent.state import AgentState
from app.agent.graph import app as agent_app
from app.agent.memory import make_key, load_state, save_state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/agent", response_model=AgentResponse)
async def run_agent_endpoint(request: AgentRequest) -> AgentResponse:
    """
    Main entrypoint for the AI agent.

    Responsibilities:
    - Resolve memory scope using (session_id, problem_id, scenario_ids)
    - Load existing AgentState or create a new one
    - Inject the new user message and data
    - Run LangGraph
    - Persist updated state
    - Return structured response
    """

    try:
        # build conversation memory key
        # if not request.session_id:
        #     raise HTTPException(
        #         status_code=400,
        #         detail="session_id is required for agent memory scoping",
        #     )

        key = make_key(
            session_id=request.session_id,
            problem_id=request.problem_id,
            scenario_ids=request.scenario_ids,
        )

        # load or initialize agent state
        state = load_state(key)

        # update state with incoming request
        state.session_id = request.session_id
        state.problem_id = request.problem_id or ""
        state.scenario_ids = request.scenario_ids or []
        state.user_message = request.user_message
        if request.data is not None:
            state.data = request.data
            state.data_loaded_at = request.data_loaded_at
        state.current_input = request.current_input or state.current_input
        state.awaiting_confirmation = request.awaiting_confirmation or False
        state.running_scenario = request.running_scenario or False

        # reset per-turn outputs
        state.response = ""
        state.next_action = None

        logger.info(
            "Running agent | session=%s problem=%s scenarios=%s",
            request.session_id,
            request.problem_id,
            request.scenario_ids,
        )

        # run the LangGraph agent, persist and return state
        final_state = AgentState(**agent_app.invoke(state))
        save_state(key, final_state)
        return AgentResponse(
            action=final_state.next_action,
            response=final_state.response,
            blocked=getattr(final_state, "blocked", None),
            state=final_state.__dict__,  # full state for debugging / UI
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )
