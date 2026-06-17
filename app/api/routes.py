# SPDX-License-Identifier: Apache-2.0

from fastapi import (APIRouter,
                     HTTPException,
                     UploadFile,
                     BackgroundTasks,
                     File, Form, Body)
from fastapi.responses import StreamingResponse
import logging
import asyncio

from app.schemas import AgentResponse
from app.agent.state import AgentState
from app.agent.graph_agentic import app as agent_app
from app.agent.nodes.context_management import handle_context
from app.agent.memory import generate_key, load_state, save_state
from app.utils.error_codes import get_error_message, ErrorCode
from app.agent.events import get_queue, publish_done, get_result
from app.utils.common import get_available_entries_if_missing


logger = logging.getLogger(__name__)

router = APIRouter()


def _save_conversation(session_id: str):
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID is required")

    state = load_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    state.save()
    state.dump_to_file(f"logs/state_{state.session_id}.json")
    return {"message": "Conversation saved successfully."}


def _run_agent(key: str, state: AgentState):
    """
    Runs synchronously inside a thread — never call from the event loop directly.
    """
    try:
        updated = agent_app.invoke(state)

        state_dict = {k: v for k, v in updated.items() if k != "__interrupt__"}
        final_state = AgentState(**state_dict)
        save_state(key, final_state)

        active_context = final_state.get_active_context_string()
        last_msg = final_state.get_last_message()
        response_text = (
            last_msg.content
            if last_msg and last_msg.role == "assistant"
            else get_error_message(ErrorCode.REQUEST_ERROR)
        )
        result = {
            "response": response_text,
            "session_id": key,
            "active_context": active_context,
            "chart_data": getattr(final_state, "chart_data", None),
            "sliders_data": getattr(final_state, "sliders_data", None),
        }

    except Exception as e:
        logger.exception(f"Unhandled error in _run_agent for session {key}: {e}")
        result = {
            "response": get_error_message(ErrorCode.REQUEST_ERROR),
            "session_id": key,
            "active_context": None,
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
    context: list[str] = Form(default=[])
):
    key = session_id or generate_key()
    state = load_state(key) or AgentState(
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

        # Set context on state — the graph's inject_tools node will use
        # active_context_type to filter available tools at graph entry.
        state.integrated_mode = True
        state.cognitive.previous_context = state.cognitive.active_context
        state.cognitive.active_context = context
        state.cognitive.active_context_type = "scenario"
        state = get_available_entries_if_missing(state)
        state = handle_context(state)

    # Single graph handles both modes; no graph parameter needed
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


@router.get("/agent/save/{session_id}")
async def save_conversation_get(session_id: str):
    try:
        return _save_conversation(session_id)
    except Exception as e:
        logger.exception("Failed to save conversation")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save conversation: {str(e)}",
        )


@router.post("/agent/inject_sliders")
async def inject_sliders_endpoint(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...)
):
    try:
        logger.info(f"Received slider indexes {payload}")
        session_id = payload.get("session_id")
        index_diffs = payload.get("values", {})

        state = load_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        state.cognitive.scenario_validated_indexes = index_diffs
        state.sliders_data = None
        state.user_input = "Send index change via interface"
        logger.info(f"Injected sliders for session: {index_diffs}")

        # integrated_mode is already set on the persisted state, so the graph's
        # resume_router will correctly route to inject_tools on next invocation
        background_tasks.add_task(asyncio.to_thread, _run_agent, session_id, state)

        return {"session_id": session_id}

    except Exception as e:
        logger.exception("Failed to inject sliders")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to inject sliders: {str(e)}",
        )


@router.post("/agent/feedback")
async def submit_feedback(payload: dict = Body(...)):
    session_id = payload.get("session_id")
    message_index = payload.get("message_index")
    vote = payload.get("vote")
    comment = payload.get("comment")

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

    msg.vote = vote
    msg.comment = comment

    save_state(session_id, state)
    return {"message": "Feedback saved."}


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

    normalized_vote = vote if vote in {"up", "down"} else None
    msg.vote = normalized_vote
    msg.comment = comment

    save_state(session_id, state)
    return {"message": "Feedback saved."}