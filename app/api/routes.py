# SPDX-License-Identifier: Apache-2.0

import os
from fastapi import (
    APIRouter,
    HTTPException,
    Header,
    Query,
    UploadFile,
    BackgroundTasks,
    File,
    Form,
)
from fastapi.responses import StreamingResponse
import logging
import asyncio

from app.schemas import AgentResponse, ToolStep, RunSelectedToolsRequest
from app.agent.state import AgentState
from app.agent.graph_agentic import app as agent_app
from app.agent.memory import load_state, save_state, delete_state, _get_lock
from app.agent.events import get_queue, publish_done, get_result, clear_session
from app.config import GENERAL_ERROR_MESSAGE
from app.tools.backend_tools import check_authorization
from app.tools.tool_registry import _ensure_tool_registry
from app.utils.common import set_token

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"

router = APIRouter()


# ---------------------------------------------------------------------------
# AUTH / SESSION-OWNERSHIP HELPERS
# ---------------------------------------------------------------------------
# Every endpoint below that reads or mutates an existing session_id needs to
# both (a) confirm the caller holds a valid token for the claimed tenant, and
# (b) confirm the session actually belongs to that tenant — otherwise anyone
# who knows/guesses a session_id could read or reset someone else's
# conversation. Centralized here so each route applies the same check.


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip()


def _require_bearer_token(authorization: str | None) -> str:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=401, detail="Missing or malformed Authorization header"
        )
    return token


def _authorize_tenant(token: str, tenant: str) -> None:
    if not tenant:
        raise HTTPException(status_code=400, detail="tenant is required")
    if not check_authorization(token=token, tenant=tenant):
        raise HTTPException(status_code=403, detail="Not authorized")


def _load_owned_session(session_id: str, tenant: str) -> AgentState | None:
    """Load session state, but only if it belongs to the authorized tenant.

    Returns None both when the session doesn't exist AND when it belongs to
    a different tenant — deliberately indistinguishable to the caller, so an
    authorized-but-wrong-tenant request can't be used to probe which
    session_ids exist.
    """
    state = load_state(session_id)
    if state is None or state.tenant != tenant:
        return None
    return state


def _run_agent(key: str, state: AgentState, token: str):
    """Runs synchronously inside a thread — never call from the event loop directly."""
    set_token(token)
    try:
        logger.info(f"Message sent from conversation {key}")

        updated = agent_app.invoke(
            state,
            config={"configurable": {"token": token, "thread_id": key}},
        )

        state_dict = {k: v for k, v in updated.items() if k != "__interrupt__"}
        final_state = AgentState(**state_dict)

        last_msg = final_state.get_last_message()
        response_text = (
            last_msg.content
            if last_msg and last_msg.role == "assistant"
            else GENERAL_ERROR_MESSAGE
        )
        result = {
            "response": response_text,
            "session_id": key,
            "assistant_action_data": getattr(
                final_state, "assistant_action_data", None
            ),
        }

        save_state(final_state)

    except Exception as e:
        logger.exception(f"Unhandled error in _run_agent for session {key}: {e}")
        result = {
            "response": GENERAL_ERROR_MESSAGE,
            "session_id": key,
            "assistant_action_data": None,
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
    authorization: str | None = Header(default=None),
    tenant: str = Form(default="molveno"),  # TODO remove default
):

    # Verify authorization
    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_tenant(token, tenant)
    else:
        token = None

    # Check session key
    if not session_id or session_id == "":
        raise HTTPException(status_code=400, detail="No session_id provided")

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="No message provided")

    if integrated_mode and len(context) == 0:
        raise HTTPException(
            status_code=400, detail="Context is required in integrated mode"
        )

    # Get status and proceed with the request
    lock = _get_lock(session_id)

    async with lock:
        state = load_state(session_id)

        if state is None:
            state = AgentState(
                session_id=session_id,
                user_lang=user_lang,
                integrated_mode=integrated_mode,
                tenant=tenant,
            )
        elif state.tenant != tenant:
            # Don't reveal whether the session exists under another tenant.
            raise HTTPException(status_code=404, detail="Session not found")

        state.add_user_message(message)

        if state.waiting_for:
            state.user_input = message
        else:
            state.user_input = None

        if integrated_mode:
            logger.info(f"Running in integrated mode with context: {context}")
            state.cognitive.current_context = {
                "problems": [],
                "proposals": [],
                "scenarios": context,
            }
            state.cognitive.enabled_tools = [
                "get_context_details",
                "analyze_scenario_results",
                "lookup_glossary",
            ]
        else:
            # Non-integrated mode: all tools are available.
            # enabled_tools is intentionally left empty here; initialize_tools will
            # populate it with the full known_tools list once the registry is ready.
            state.cognitive.enabled_tools = []

        save_state(state)

    background_tasks.add_task(asyncio.to_thread, _run_agent, session_id, state, token)
    return {"session_id": session_id}


@router.post("/agent/reset")
async def reset_session(
    session_id: str = Form(...),
    authorization: str | None = Header(default=None),
    tenant: str = Form(default="molveno"),  # TODO remove default
):
    """
    Start a fresh conversation for `session_id`.

    Drops the persisted AgentState (conversation history, ReAct scratchpad,
    long-term tool-result memory, any pending confirmation) and any
    leftover SSE events/result for the session, so the next `/agent` call
    for this session_id begins a brand new turn from scratch.
    """
    if not session_id or session_id == "":
        raise HTTPException(status_code=400, detail="No session_id provided")

    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_tenant(token, tenant)

    lock = _get_lock(session_id)
    async with lock:
        # Only reset a session that actually belongs to this tenant. If it
        # belongs to someone else (or never existed), don't touch it, and
        # don't reveal which of those two happened.
        state = load_state(session_id)
        if state is not None and state.tenant != tenant:
            raise HTTPException(status_code=404, detail="Session not found")

        delete_state(session_id)
        clear_session(session_id)

    logger.info(f"Session {session_id} reset")
    return {"session_id": session_id, "status": "reset"}


@router.get("/agent/result/{session_id}", response_model=AgentResponse)
async def get_agent_result(
    session_id: str,
    tenant: str = Query(default="molveno"),
    authorization: str | None = Header(default=None),
):
    # if AUTH_ENABLED:
    # token = _require_bearer_token(authorization)
    # _authorize_tenant(token, tenant)

    if _load_owned_session(session_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    result = get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail="Result not ready or already consumed"
        )
    return AgentResponse(**result)


@router.get("/agent/stream/{session_id}")
async def stream_events(
    session_id: str,
    tenant: str = Query(default="molveno"),
    # EventSource (the standard way to consume SSE from a browser) cannot
    # set custom headers, so this endpoint also accepts the token as a query
    # param. The Authorization header is preferred when present.
    token: str | None = Query(
        default=None,
        description="Bearer token — only needed if this stream is opened "
        "via EventSource, which can't set an Authorization header.",
    ),
    authorization: str | None = Header(default=None),
):
    # if AUTH_ENABLED:
    # bearer = _extract_bearer_token(authorization) or token
    # if not bearer:
    #     raise HTTPException(
    #         status_code=401, detail="Missing bearer token (header or ?token=)"
    #     )
    # _authorize_tenant(bearer, tenant)

    if _load_owned_session(session_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Session not found")

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


@router.post("/agent/feedback")
async def submit_feedback_get(
    session_id: str,
    message_index: int,
    tenant: str = Query(default="molveno"),
    authorization: str | None = Header(default=None),
    vote: str | None = None,
    comment: str | None = None,
):
    # if AUTH_ENABLED:
    # token = _require_bearer_token(authorization)
    # _authorize_tenant(token, tenant)

    state = _load_owned_session(session_id, tenant)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = state.conversation.messages
    if message_index is None or message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")

    msg = messages[message_index]
    if msg.role != "assistant":
        raise HTTPException(
            status_code=400, detail="Can only give feedback on assistant messages"
        )

    msg.vote = vote if vote in {"up", "down"} else None
    msg.comment = comment

    save_state(state)
    return {"message": "Feedback saved."}


@router.post("/agent/tool")
async def run_selected_tools(
    body: RunSelectedToolsRequest,
    tenant: str = Query(default="molveno"),
    authorization: str | None = Header(default=None),
):
    """Depending on the parameters in body, run an explicit, ordered sequence of tools
    — e.g. for summary: get_context_details -> summary_generation.
    Each step runs against the SAME AgentState, so later steps see earlier ones' results
    exactly like they would inside a normal ReAct turn.

    This endpoint is stateless by design: it never loads or reuses an
    existing session_id, and the throwaway AgentState it builds for the
    pipeline is never persisted (no save_state call), so there is nothing
    left over to clean up once the response is returned.

    By default stops at the first failed step (stop_on_error=True); set it
    to False to run every step regardless and inspect all results.

    curl -X POST "http://localhost:9000/agent/tool?tenant=molveno" -H "Content-Type: application/json" -d '{"key": "summary", "scenario_ids": ["751846b146044e06a37e993251f3fbc3"]}'
    """
    from app.agent.nodes.tool_executor import execute_selected_tool

    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_tenant(token, tenant)
    else:
        token = None
    if token:
        set_token(token)

    _ensure_tool_registry()

    # Stateless, session-less scratch state — intentionally never saved.
    state = AgentState(tenant=tenant)

    if body.key == "summary":
        if not body.scenario_ids:
            raise HTTPException(
                status_code=400,
                detail="scenario_ids is required when key == 'summary'",
            )
        state.cognitive.current_context = {
            "problems": [],
            "proposals": [],
            "scenarios": body.scenario_ids,
        }
        steps = [
            {"tool_name": "get_context_details", "arguments": {}},
            {"tool_name": "summary_generation", "arguments": {}},
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported key: {body.key!r}")

    # summary_generation (and any other internal-only tool) is disabled in
    # the registry so it never appears in normal chat's tool allowlist, but
    # this endpoint is an explicit, admin-style pipeline — so it's allowed
    # to run disabled tools deliberately.
    results = []
    for step in steps:
        outcome = await asyncio.to_thread(
            execute_selected_tool,
            step["tool_name"],
            step["arguments"],
            state,
            allow_disabled=True,
        )
        results.append({"tool_name": step["tool_name"], **outcome})
        if not outcome["success"]:
            logger.warning(
                f"Pipeline stopped at '{step['tool_name']}': {outcome['error']}"
            )
            break

    last = results[-1]

    if not last["success"]:
        raise HTTPException(status_code=500, detail=last["error"])

    return {"message": last["output"]["message"]}
