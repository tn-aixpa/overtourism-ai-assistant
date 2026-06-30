# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException, UploadFile, BackgroundTasks, File, Form
from fastapi.responses import StreamingResponse
import logging
import asyncio

from app.schemas import AgentResponse
from app.agent.state import AgentState
from app.agent.graph_agentic import app as agent_app
from app.agent.memory import generate_key, load_state, save_state, _get_lock
from app.utils.error_codes import get_error_message, ErrorCode
from app.agent.events import get_queue, publish_done, get_result

logger = logging.getLogger(__name__)

router = APIRouter()

def _run_agent(key: str, state: AgentState):
    """Runs synchronously inside a thread — never call from the event loop directly."""
    try:
        logger.info(f"Message sent from conversation {key}")

        updated = agent_app.invoke(state)

        state_dict = {k: v for k, v in updated.items() if k != "__interrupt__"}
        final_state = AgentState(**state_dict)

        last_msg = final_state.get_last_message()
        response_text = (
            last_msg.content
            if last_msg and last_msg.role == "assistant"
            else get_error_message(ErrorCode.REQUEST_ERROR)
        )
        result = {
            "response": response_text,
            "session_id": key,
            "chart_data": getattr(final_state, "chart_data", None),
            "sliders_data": getattr(final_state, "sliders_data", None),
        }

        save_state(final_state)

    except Exception as e:
        logger.exception(f"Unhandled error in _run_agent for session {key}: {e}")
        result = {
            "response": get_error_message(ErrorCode.REQUEST_ERROR),
            "session_id": key,
            "chart_data": None,
            "sliders_data": None,
        }

    finally:
        publish_done(key, result)


@router.post("/agent", status_code=202)
async def run_agent_endpoint(
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    user_lang: str = Form(default="English"),
    session_id: str = Form(...),
    files: list[UploadFile] = File([]),
    integrated_mode: bool = Form(default=False),
    context: list[str] = Form(default=[]),
):
    key = session_id or generate_key()
    lock = _get_lock(key)

    async with lock:
        state = load_state(key)
        if state is None:
            state = AgentState(
                session_id=key,
                user_lang=user_lang,
                integrated_mode=integrated_mode,
            )

        assert message, "No message provided"
        state.add_user_message(message)

        if state.waiting_for:
            state.user_input = message
        else:
            state.user_input = None

        if integrated_mode:
            logger.info(f"Running in integrated mode with context: {context}")
            assert len(context) > 0, "Context is required in integrated mode"
            state.cognitive.current_context = {
                "problems": [],
                "proposals": [],
                "scenarios": context,
            }
            state.cognitive.enabled_tools = [
                "get_context_details",
                "interact_with_context",
                "lookup_glossary",
            ]
        else:
            # Non-integrated mode: all tools are available.
            # enabled_tools is intentionally left empty here; initialize_tools will
            # populate it with the full known_tools list once the registry is ready.
            state.cognitive.enabled_tools = []

        save_state(state)

    background_tasks.add_task(asyncio.to_thread, _run_agent, key, state)
    return {"session_id": key}


@router.get("/agent/result/{session_id}", response_model=AgentResponse)
async def get_agent_result(session_id: str):
    result = get_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not ready or already consumed")
    return AgentResponse(**result)


@router.get("/agent/stream/{session_id}")
async def stream_events(session_id: str):
    queue = get_queue(session_id)

    async def event_generator():
        while True:
            event = await asyncio.to_thread(queue.get)
            logger.info(f"Sending SSE event: {event}")
            if event == "__done__":
                yield "event: done\ndata: \n\n"
                break
            yield f"event: status\ndata: {event}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/agent/feedback")
async def submit_feedback_get(
    session_id: str,
    message_index: int,
    vote: str | None = None,
    comment: str | None = None,
):
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID is required")

    state = load_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = state.conversation.messages
    if message_index is None or message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")

    msg = messages[message_index]
    if msg.role != "assistant":
        raise HTTPException(status_code=400, detail="Can only give feedback on assistant messages")

    msg.vote = vote if vote in {"up", "down"} else None
    msg.comment = comment

    save_state(state)
    return {"message": "Feedback saved."}