# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
import logging

from app.schemas import AgentResponse
from app.agent.state import AgentState
from app.agent.graph import app as agent_app
from app.agent.memory import generate_key, load_state, save_state
from app.utils.error_codes import get_error_message, ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/agent", response_model=AgentResponse)
async def run_agent_endpoint(
    message: str = Form(...),
    user_lang: str = Form(default="English"),
    session_id: str = Form(...),
    files: list[UploadFile] = File([]),
) -> AgentResponse:
    try:
        key = session_id or generate_key()
        state = load_state(key)
        if not state:
            state = AgentState(session_id=key, user_lang=user_lang)

        assert message, "No message provided in the request"
        logger.info(f"Received message for session {key}: {message} ({len(files)} attachments)")
        state.add_user_message(message)

        if state.waiting_for:
            state.user_input = message
        else:
            state.user_input = None

        updated_state_dict = agent_app.invoke(state)
        state_dict = {k: v for k, v in updated_state_dict.items() if k != "__interrupt__"}
        final_state = AgentState(**state_dict)
        save_state(key, final_state)

        active_context = final_state.get_active_context_string()
        last_msg = final_state.get_last_message()
        response_text = (
            last_msg.content
            if last_msg and last_msg.role == "assistant"
            else get_error_message(ErrorCode.REQUEST_ERROR)
        )

        # NEW: pull chart_data from state (None if no chart was generated this turn)
        chart_data = getattr(final_state, "chart_data", None)

        return AgentResponse(
            response=response_text,
            session_id=key,
            active_context=active_context,
            chart_data=chart_data,   # <-- new field
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent execution failed")
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")


@router.post("/agent/save")
async def save_conversation_endpoint(payload: dict = Body(...)):
    try:
        session_id = payload.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        state = load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        state.save()
        state.dump_to_file(f"logs/state_{state.session_id}.json")
        return {"message": "Conversation saved successfully."}
    except Exception as e:
        logger.exception("Failed to save conversation")
        raise HTTPException(status_code=500, detail=f"Failed to save conversation: {str(e)}")
