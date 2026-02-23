# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException
import logging
from datetime import datetime

from app.schemas import AgentRequest, AgentResponse
from app.agent.state import AgentState, ConversationMessage
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
            scenario_ids=request.cognitive.scenario_ids,
        )

        # load or initialize agent state
        state = load_state(key)

        # parse request message
        message = request.message if request.message else ""

        # update state with incoming request
        state.session_id = request.session_id
        state.cognitive.problem_id = request.problem_id or ""
        state.cognitive.scenario_ids = request.cognitive.scenario_ids or []
        state.conversation.append(
            ConversationMessage(
                role="user",
                content=message,
                timestamp=datetime.now()
        ))
        state.last_user_en=message
        if request.cognitive.data is not None:
            state.cognitive.data = request.cognitive.data

        # reset per-turn outputs
        state.cognitive.next_action = None

        logger.info(
            "Running agent | session=%s problem=%s scenarios=%s",
            request.session_id,
            request.problem_id,
            request.cognitive.scenario_ids,
        )

        # run the LangGraph agent, persist and return state
        final_state = AgentState(**agent_app.invoke(state))
        save_state(key, final_state)
        response = final_state.conversation[-1].content if final_state.conversation and final_state.conversation[-1].role == "assistant" else "ERROR: No assistant message generated"
        return AgentResponse(
            action=final_state.cognitive.next_action,
            response=response,
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
