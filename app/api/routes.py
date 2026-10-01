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
import queue

from app.schemas import AgentResponse, RunSelectedToolsRequest
from app.agent.state import AgentState
from app.agent.graph_agentic import app as agent_app
from app.agent.memory import (
    load_state,
    save_state,
    delete_state,
    _get_lock,
    is_in_flight,
    mark_in_flight,
    clear_in_flight,
)
from app.agent.events import get_queue, publish_done, get_result, clear_session
from app.tools.tool_registry import _ensure_tool_registry
from app.utils.common import set_token
from app.utils.authentication import (
    _require_bearer_token,
    _authorize_territory,
    get_user_id,
    get_user_role,
)

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
DISABLE_INTEGRATED = os.environ.get("DISABLE_INTEGRATED", "true").lower() == "true"

router = APIRouter()


def _load_owned_session(session_id: str, territory: str) -> AgentState | None:
    """Load session state, but only if it belongs to the authorized territory.

    Returns None both when the session doesn't exist AND when it belongs to
    a different territory — deliberately indistinguishable to the caller, so an
    authorized-but-wrong-territory request can't be used to probe which
    session_ids exist.
    """
    state = load_state(session_id)
    if state is None or state.territory != territory:
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
            else "System error"
        )
        result = {
            "response": response_text,
            "session_id": key,
            "agent_type": final_state.active_agent.value,
            "assistant_action_data": getattr(
                final_state, "assistant_action_data", None
            ),
        }

        save_state(final_state)

    except Exception as e:
        logger.exception(f"Unhandled error in _run_agent for session {key}: {e}")
        result = {
            "response": "System error",
            "session_id": key,
            "assistant_action_data": None,
        }

    finally:
        publish_done(key, result)
        # Must be cleared even on the exception path above, or a session
        # that errors once would stay "in flight" forever and every
        # subsequent /agent call for it would 409 permanently.
        clear_in_flight(key)


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
    tenant: str = Query(...),
):
    if integrated_mode and DISABLE_INTEGRATED:
        state = AgentState(
            session_id=session_id,
            user_id="system",
            integrated_mode=True,
            territory=tenant,
            user_role="standard",
            session_mode="internal",
        )

        save_state(state)

        result = {
            "response": "Al momento l'assistente integrato non è disponibile",
            "session_id": session_id,
            "assistant_action_data": None,
        }

        # Whatever mechanism your frontend expects for completion:
        publish_done(session_id, result)

        return {"session_id": session_id}

    # Verify authorization
    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_territory(token, tenant)
    else:
        token = None

    # Check session key
    if not session_id or session_id == "":
        raise HTTPException(status_code=400, detail="No session_id provided")

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="No message provided")

    # Get status and proceed with the request
    lock = _get_lock(session_id)

    async with lock:
        # Reject a second message for this session while the previous one's
        # background turn is still running, instead of silently racing on
        # it (see the long comment on _IN_FLIGHT in memory.py for exactly
        # what that race does: shared-object corruption, a non-atomically
        # overwritten JSON dump, and a completed response that's generated
        # but never reaches the frontend because the SSE stream already
        # closed after the OTHER turn's "__done__"). Checked/marked inside
        # this same lock so two requests arriving back-to-back can't both
        # pass the check before either sets the flag.
        if is_in_flight(session_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "A previous message for this session is still being "
                    "processed. Wait for it to finish before sending "
                    "another."
                ),
            )

        state = load_state(session_id)

        if state is None:
            user_id = get_user_id(token)

            state = AgentState(
                session_id=session_id,
                user_id=user_id,
                user_lang=user_lang,
                integrated_mode=integrated_mode,
                territory=tenant,
                user_role=get_user_role(token),
                # Fixed for the session's whole lifetime, same as
                # integrated_mode itself (see the note below on why every
                # later turn must branch on persisted state, not the raw
                # form field).
                session_mode="internal" if integrated_mode else "standalone",
            )
        elif state.territory != tenant:
            # Don't reveal whether the session exists under another territory.
            raise HTTPException(status_code=404, detail="Session not found")

        # A session's mode is fixed for its whole lifetime (set once, above,
        # when the session is first created) — see reasoner.initialize_tools.
        # Always branch on the PERSISTED state.integrated_mode from here on,
        # never on this request's raw `integrated_mode` form field: a
        # follow-up call that simply omits/defaults that field (e.g. the
        # frontend only sends it on the first turn) must not silently make
        # an integrated session behave as standalone for the rest of the
        # conversation — that was dropping `context` on every turn after
        # the first instead of re-resolving it.
        if state.integrated_mode and len(context) == 0:
            raise HTTPException(
                status_code=400, detail="Context is required in integrated mode"
            )

        state.add_user_message(message)

        if state.waiting_for:
            state.user_input = message
        else:
            state.user_input = None

        if state.integrated_mode:
            logger.info(f"Running in integrated mode with context: {context}")

            def _extract(prefix: str) -> list[str]:
                return [c.split(":", 1)[1] for c in context if c.startswith(prefix)]

            state.cognitive.current_context = {
                "problems": _extract("problem:"),
                "proposals": _extract("proposal:"),
                "scenarios": _extract("scenario:"),
            }

        # Both modes leave enabled_tools empty here; initialize_tools
        # populates it fresh from the full known_tools list once the
        # registry is ready. Integrated sessions get every tool a
        # standalone session gets EXCEPT widget tools (show_analysis_widget,
        # show_territorial_index_map) — that exclusion is declared on the
        # tools themselves (ToolDefinition.allowed_modes={"standalone"})
        # and enforced generically by ToolRegistry.get_context_tools via
        # state.session_mode, not hardcoded here, so the two modes can't
        # silently drift apart on which non-widget tools are available.
        state.cognitive.enabled_tools = []

        save_state(state)
        mark_in_flight(session_id)

    background_tasks.add_task(asyncio.to_thread, _run_agent, session_id, state, token)
    return {"session_id": session_id}


@router.post("/agent/reset")
async def reset_session(
    session_id: str = Form(...),
    authorization: str | None = Header(default=None),
    tenant: str = Query(...),
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
        _authorize_territory(token, tenant)

    lock = _get_lock(session_id)
    async with lock:
        # Only reset a session that actually belongs to this territory. If it
        # belongs to someone else (or never existed), don't touch it, and
        # don't reveal which of those two happened.
        state = load_state(session_id)
        if state is not None and state.tenant != tenant:
            raise HTTPException(status_code=404, detail="Session not found")

        delete_state(session_id)
        clear_session(session_id)
        # delete_state() already clears this, but stated explicitly here
        # too: a reset must never leave a session permanently 409-ing on
        # every future /agent call because it happened to fire while a
        # turn was still in flight.
        clear_in_flight(session_id)

    logger.info(f"Session {session_id} reset")
    return {"session_id": session_id, "status": "reset"}


@router.get("/agent/result/{session_id}", response_model=AgentResponse)
async def get_agent_result(
    session_id: str,
    tenant: str = Query(...),
    authorization: str | None = Header(default=None),
):
    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_territory(token, tenant)

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
    tenant: str = Query(...),
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
    if AUTH_ENABLED:
        # Native browser EventSource cannot set arbitrary request headers, so
        # accept the token from the query string as a fallback. Prefer the
        # Authorization header when the client can provide it.
        auth_header = authorization
        if not auth_header and token:
            auth_header = f"Bearer {token}"
        token = _require_bearer_token(auth_header)
        _authorize_territory(token, tenant)

    if _load_owned_session(session_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    event_queue = get_queue(session_id)

    async def event_generator():
        # Never leave an SSE connection blocked forever. Periodic comments keep
        # proxies/load-balancers from considering the response idle, while the
        # timeout also lets us recover cleanly if the client connects after the
        # completion event has already been published. The final response is
        # available through /agent/result/{session_id}.
        while True:
            try:
                event = await asyncio.to_thread(event_queue.get, True, 30)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            except Exception as exc:
                logger.exception(f"SSE queue failure for session {session_id}: {exc}")
                break

            logger.info(f"Sending SSE event for session {session_id}: {event}")

            if event == "__done__":
                yield "event: done\ndata: \n\n"
                break

            yield f"event: status\ndata: {event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/feedback")
async def submit_feedback_get(
    session_id: str,
    message_index: int,
    tenant: str = Query(...),
    authorization: str | None = Header(default=None),
    vote: str | None = None,
    comment: str | None = None,
):
    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_territory(token, tenant)

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
    tenant: str = Query(...),
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

    """
    from app.agent.nodes.tool_executor import execute_selected_tool

    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_territory(token, tenant)
    else:
        token = None
    if token:
        set_token(token)

    _ensure_tool_registry()

    # Stateless, session-less scratch state — intentionally never saved.
    user_id = get_user_id(token) + "-system"
    state = AgentState(
        territory=tenant,
        user_id=user_id,
        user_role=get_user_role(token),
        # This pipeline runs outside the normal chat surface entirely —
        # not "standalone" or "internal" — so it gets its own SessionMode
        # value. Tools that should ONLY ever be reachable through this
        # pipeline (summary_generation, report_generation) declare
        # allowed_modes={"system"} accordingly (see below).
        session_mode="system",
    )

    if body.key == "summary":
        if not body.current_context:
            raise HTTPException(
                status_code=400,
                detail="scenario_ids is required when key == 'summary'",
            )
        state.cognitive.current_context = body.current_context
        steps = [
            {"tool_name": "get_context_details", "arguments": {}},
            {"tool_name": "summary_generation", "arguments": {}},
        ]
    elif body.key == "pdf-report":
        if not body.current_context:
            raise HTTPException(
                status_code=400,
                detail="at least one problem, proposal or scenario has to be specified",
            )
        state.cognitive.current_context = body.current_context
        steps = [
            {"tool_name": "get_context_details", "arguments": {}},
            {"tool_name": "report_generation", "arguments": {}},
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported key: {body.key!r}")

    # summary_generation / report_generation are disabled in the registry
    # (enabled=False) so they never appear in normal chat's tool allowlist,
    # AND declare allowed_modes={"system"} so they can only ever be
    # selected/executed from this pipeline. allow_disabled=True below
    # deliberately bypasses only the `enabled` flag — the allowed_modes
    # check in execute_selected_tool still applies and passes here because
    # state.session_mode is "system" (set above).
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


@router.get("/agent/usage_stats")
async def get_usge_stats(
    authorization: str | None = Header(default=None),
):
    # Verify authorization
    if AUTH_ENABLED:
        token = _require_bearer_token(authorization)
        _authorize_territory(token, "default")
    else:
        token = None

    from app.utils.token_tacking import get_usage_per_day

    return get_usage_per_day()
