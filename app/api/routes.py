# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException
import logging

from app.schemas import AgentRequest, AgentResponse
from app.agent.state import AgentState, ConversationBuffer, CognitiveState
from app.agent.graph import app as agent_app
from app.agent.memory import generate_key, load_state, save_state
from app.utils.common import translate_from_eng
from app.utils.error_codes import get_error_message

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
        # load or initialize agent state
        key = request.session_id or None
        #state = load_state(key)

        # parse request message
        message = request.message if request.message else ""
        
        # TODO: parse other parts if needed and remove create from scratch logic
        state = AgentState(
            conversation=ConversationBuffer(),
            session_id="",
            user_lang="English",
            cognitive=CognitiveState()
        )

        state.add_user_message(message, translate_from_eng(message, state.user_lang))

        # run the LangGraph agent, persist and return state
        final_state = AgentState(**agent_app.invoke(state))
        
        #save_state(key, final_state)

        last_message = final_state.get_last_message()
        response = last_message.content_en if last_message and last_message.role == "assistant" else ""
        
        return AgentResponse(
            response=response,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )
