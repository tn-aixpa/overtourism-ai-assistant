# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException
import logging
from datetime import datetime

from app.schemas import AgentRequest, AgentResponse
from app.agent.state import AgentState, ConversationMessage
from app.agent.graph import app as agent_app
from app.agent.memory import generate_key, load_state, save_state
from app.utils.common import translate_from_eng
from app.utils.error_codes import ErrorCode, get_error_message

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
        key = generate_key()

        # load or initialize agent state
        state = load_state(key)

        # parse request message
        message = request.message if request.message else ""

        # update state with incoming request
        state.session_id = request.session_id
        state.cognitive.problem_id = request.problem_id or ""
        state.cognitive.scenario_ids = request.cognitive.scenario_ids or []
        state.add_user_message(message, translate_from_eng(message, state.user_lang))
        if request.cognitive.data is not None:
            state.cognitive.data = request.cognitive.data

        # reset per-turn outputs
        state.cognitive.next_action = None

        logger.info(
            "Running agent | session=%s problem=%s scenarios=%s",
            request.session_id,
            request.cognitive.problem_id,
            request.cognitive.scenario_ids,
        )

        # run the LangGraph agent, persist and return state
        final_state = AgentState(**agent_app.invoke(state))
        save_state(key, final_state)
        last_message = final_state.get_last_message()
        response = last_message.content_localized if last_message and last_message.role == "assistant" else get_error_message(ErrorCode.INVALID_REQUEST, state.user_lang)
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
