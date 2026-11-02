# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import time as _t
import uuid
from concurrent.futures import ThreadPoolExecutor as _TPE
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from app.schemas import RunSelectedToolsRequest
from app.agent.state import AgentState
from app.agent.graph_agentic import app as agent_app
from app.agent.memory import (
    load_state,
    save_state,
    remember_state,
    persist_state,
    delete_state,
    _get_lock,
)
from app.agent.events import (
    TurnInProgress,
    clear_session,
    iter_sse,
    store,
    turn_context,
)
from app.tools.tool_registry import _ensure_tool_registry
from app.utils.common import set_token
from app.utils.authentication import (
    _require_bearer_token,
    check_authorization,
)
from app.utils.backend_utils import get_allowed_territories

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"

# Hard ceiling for one agent turn. If the turn thread is stuck (a hung backend
# or LLM call, ...) the turn is closed as "timeout" so the client always gets
# a terminal state instead of waiting forever.
AGENT_TURN_TIMEOUT = float(os.environ.get("AGENT_TURN_TIMEOUT", "300"))

router = APIRouter()

# Agent turns are long (tens of seconds of LLM/backend waiting). Give them their
# OWN pool so they can never starve the short blocking calls (auth, state save)
# that share the default asyncio executor.
_TURN_POOL = _TPE(
    max_workers=int(os.environ.get("AGENT_MAX_CONCURRENT_TURNS", "64")),
    thread_name_prefix="agent-turn",
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
_AUTH_CACHE: dict[str, tuple[float, tuple]] = {}
_AUTH_TTL = 30.0


def _cached_check_authorization(token: str):
    hit = _AUTH_CACHE.get(token)
    if hit and hit[0] > _t.monotonic():
        return hit[1]
    res = check_authorization(token)
    if res[0]:
        _AUTH_CACHE[token] = (_t.monotonic() + _AUTH_TTL, res)
    return res


def _require_authorized_user(token: str) -> tuple[str, str]:
    authorized, role, user_id = _cached_check_authorization(token)
    if not authorized:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return role, user_id


async def _authenticate(authorization: str | None) -> tuple[str | None, str, str]:
    """-> (token, role, user_id). Also works with AUTH_ENABLED=false (the old
    code left user_id/user_role unbound in that case)."""
    if not AUTH_ENABLED:
        return None, "viewer", "anonymous"
    token = _require_bearer_token(authorization)
    role, user_id = await asyncio.to_thread(_require_authorized_user, token)
    return token, role, user_id


def _assert_owner(session_id: str, user_id: str) -> AgentState:
    """404 (not 403) so session ids can't be probed."""
    state = load_state(session_id)
    if state is None or state.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


def _result(
    session_id: str,
    response: str,
    agent_type: str | None = None,
    assistant_action_data=None,
) -> dict:
    out = {
        "response": response,
        "session_id": session_id,
        "assistant_action_data": assistant_action_data,
    }
    if agent_type is not None:
        out["agent_type"] = agent_type
    return out


def _apply_context(state: AgentState, context: list[str]) -> None:
    def _extract(prefix: str) -> list[str]:
        return [c.split(":", 1)[1] for c in context if c.startswith(prefix)]

    state.cognitive.current_context = {
        "problems": _extract("problem:"),
        "proposals": _extract("proposal:"),
        "scenarios": _extract("scenario:"),
    }


# ---------------------------------------------------------------------------
# Running a turn
# ---------------------------------------------------------------------------
async def _run_agent_in_pool(
    session_id: str, turn_id: str, state: AgentState, token: str | None
):
    loop = asyncio.get_running_loop()

    def _on_timeout() -> None:
        logger.error(
            f"Turn {turn_id} (session {session_id}) exceeded {AGENT_TURN_TIMEOUT}s"
        )
        store.finish(
            turn_id,
            "timeout",
            _result(
                session_id,
                "The request took too long to complete. Please try again.",
                state.active_agent.value,
            ),
        )

    # call_later runs on the event loop: no extra Timer thread per turn.
    watchdog = loop.call_later(AGENT_TURN_TIMEOUT, _on_timeout)
    try:
        await loop.run_in_executor(
            _TURN_POOL, _run_agent, session_id, turn_id, state, token
        )
    except BaseException:
        # e.g. executor refused the job: never leave the turn "running".
        store.finish(turn_id, "failed", _result(session_id, "System error"))
        raise
    finally:
        watchdog.cancel()


def _run_agent(session_id: str, turn_id: str, state: AgentState, token: str | None):
    """Runs in a pool thread. Always ends with exactly one store.finish()."""
    status = "failed"
    result = _result(session_id, "System error")
    final_state: AgentState | None = None

    try:
        with turn_context(turn_id):
            set_token(token)
            logger.info(f"Turn {turn_id} started for session {session_id}")
            updated = agent_app.invoke(
                state,
                config={"configurable": {"token": token, "thread_id": session_id}},
            )

        state_dict = {k: v for k, v in updated.items() if k != "__interrupt__"}
        final_state = AgentState(**state_dict)

        last_msg = final_state.get_last_message()
        if last_msg and last_msg.role == "assistant":
            status = "done"
            result = _result(
                session_id,
                last_msg.content,
                final_state.active_agent.value,
                getattr(final_state, "assistant_action_data", None),
            )
    except BaseException as e:  # noqa: BLE001 - a terminal status MUST be set
        logger.exception(f"Unhandled error in turn {turn_id}: {e}")
        status, result, final_state = (
            "failed",
            _result(session_id, "System error"),
            None,
        )

    try:
        committed = store.finish(
            turn_id,
            status,
            result,
            before_commit=(
                (lambda: remember_state(final_state))
                if final_state is not None
                else None
            ),
        )
    except Exception:
        logger.exception(f"Committing turn {turn_id} failed")
        final_state = None
        committed = store.finish(turn_id, "failed", _result(session_id, "System error"))

    # Slow I/O only AFTER the client can already see the result. If the
    # watchdog won the race, committed is False and nothing is persisted.
    if committed and final_state is not None:
        try:
            persist_state(final_state)
        except Exception:
            logger.exception(f"persist_state failed for session {session_id}")


# ---------------------------------------------------------------------------
# Session / turn endpoints
# ---------------------------------------------------------------------------
@router.post("/agent/init", status_code=201)
async def init_session(
    user_lang: str = Form(default="Italian"),
    integrated_mode: bool = Form(default=False),
    context: list[str] = Form(default=[]),
    authorization: str | None = Header(default=None),
):
    """Create a session. Everything fixed for the session's lifetime is
    resolved here, once: owner, role, allowed territories, mode, language."""
    token, role, user_id = await _authenticate(authorization)
    if integrated_mode and not context:
        raise HTTPException(
            status_code=400, detail="Context is required in integrated mode"
        )

    session_id = uuid.uuid4().hex
    state = AgentState(
        session_id=session_id,
        user_id=user_id,
        user_lang=user_lang,
        integrated_mode=integrated_mode,
        allowed_territories=await asyncio.to_thread(get_allowed_territories, token),
        user_role=role,
        # Fixed for the session's whole lifetime, same as integrated_mode.
        session_mode="internal" if integrated_mode else "standalone",
    )
    if integrated_mode:
        _apply_context(state, context)
    await asyncio.to_thread(save_state, state)

    return {
        "session_id": session_id,
        "session_mode": state.session_mode,
        "allowed_territories": state.allowed_territories,
    }


@router.post("/agent", status_code=202)
async def run_agent_endpoint(
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    session_id: str = Form(...),
    files: list[UploadFile] = File([]),
    context: list[str] = Form(default=[]),  # optional update, integrated mode
    force_role: (
        Literal["executor", "operative", "methodological", "exploitative", "auto"]
        | None
    ) = Form(default=None),
    idempotency_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    """Start a turn on an existing session. Returns immediately with turn_id."""
    token, _role, user_id = await _authenticate(authorization)
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="No message provided")

    async with _get_lock(session_id):
        state = _assert_owner(session_id, user_id)

        if (
            state.integrated_mode
            and not context
            and not state.cognitive.current_context
        ):
            raise HTTPException(
                status_code=400, detail="Context is required in integrated mode"
            )

        try:
            turn_id, created = store.start_turn(session_id, idempotency_key)
        except TurnInProgress as busy:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A previous message for this session is still "
                    "being processed.",
                    "active_turn_id": busy.turn_id,
                },
            )
        if not created:  # retried POST: same turn, don't run the agent again
            return {"session_id": session_id, "turn_id": turn_id}

        # From here on we own a running turn: any failure must release it.
        try:
            # A wait/resume request continues the same logical turn, so keep
            # its forced role; otherwise the form value replaces the old one.
            if state.waiting_for is None:
                state.force_role = None if force_role in (None, "auto") else force_role
            state.add_user_message(message)
            state.user_input = message if state.waiting_for else None
            if state.integrated_mode and context:
                logger.info(f"Running in integrated mode with context: {context}")
                _apply_context(state, context)
            # initialize_tools repopulates it from the full known_tools list.
            state.cognitive.enabled_tools = []
            await asyncio.to_thread(save_state, state)
        except BaseException:
            store.finish(turn_id, "failed", _result(session_id, "System error"))
            raise

    background_tasks.add_task(_run_agent_in_pool, session_id, turn_id, state, token)
    return {"session_id": session_id, "turn_id": turn_id}


@router.get("/agent/session/{session_id}")
async def get_session(
    session_id: str,
    authorization: str | None = Header(default=None),
):
    """Lets the frontend resume after a page reload: is a turn running?"""
    _, _, user_id = await _authenticate(authorization)
    _assert_owner(session_id, user_id)
    return {
        "session_id": session_id,
        "active_turn_id": store.active_turn(session_id),
        "latest_turn_id": store.latest_turn(session_id),
    }


@router.get("/agent/turns/{turn_id}")
async def get_turn(
    turn_id: str,
    authorization: str | None = Header(default=None),
):
    """Idempotent status + result. This is the polling fallback."""
    _, _, user_id = await _authenticate(authorization)
    snap = store.get(turn_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Turn not found")
    _assert_owner(snap["session_id"], user_id)
    return {
        "turn_id": snap["turn_id"],
        "session_id": snap["session_id"],
        "status": snap["status"],  # running | done | failed | timeout
        "last_event_id": snap["last_event_id"],
        "result": snap["result"],  # null while running
    }


@router.get("/agent/turns/{turn_id}/events")
async def stream_turn_events(
    turn_id: str,
    # EventSource (the standard way to consume SSE from a browser) cannot set
    # custom headers, so this endpoint also accepts the token as a query param.
    # The Authorization header is preferred when present.
    token: str | None = Query(
        default=None,
        description="Bearer token - only needed if this stream is opened "
        "via EventSource, which can't set an Authorization header.",
    ),
    last_event_id_query: str | None = Query(default=None, alias="last_event_id"),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    authorization: str | None = Header(default=None),
):
    if not authorization and token:
        authorization = f"Bearer {token}"
    _, _, user_id = await _authenticate(authorization)

    snap = store.get(turn_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Turn not found")
    _assert_owner(snap["session_id"], user_id)

    raw = last_event_id_header or last_event_id_query or "0"
    try:
        after = max(int(raw), 0)
    except ValueError:
        after = 0

    return StreamingResponse(
        iter_sse(turn_id, after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/reset")
async def reset_session(
    session_id: str = Form(...),
    authorization: str | None = Header(default=None),
):
    """
    Destroy the session: persisted AgentState (history, scratchpad, tool-result
    memory, pending confirmation) and every turn/event of it. A running turn
    becomes a no-op. Call /agent/init again to get a fresh session.
    """
    _, _, user_id = await _authenticate(authorization)
    async with _get_lock(session_id):
        _assert_owner(session_id, user_id)
        delete_state(session_id)
        clear_session(session_id)

    logger.info(f"Session {session_id} reset")
    return {"session_id": session_id, "status": "reset"}


# ---------------------------------------------------------------------------
# Other endpoints (unchanged apart from auth / ownership)
# ---------------------------------------------------------------------------
@router.post("/agent/feedback")
async def submit_feedback_get(
    session_id: str,
    message_index: int,
    authorization: str | None = Header(default=None),
    vote: str | None = None,
    comment: str | None = None,
):
    _, _, user_id = await _authenticate(authorization)
    state = _assert_owner(session_id, user_id)

    messages = state.conversation.messages
    if message_index is None or message_index < 0 or message_index >= len(messages):
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
    territory: str = Query(...),
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

    token, user_role, user_id = await _authenticate(authorization)
    if token:
        set_token(token)

    _ensure_tool_registry()

    allowed_territories = get_allowed_territories(token)
    if territory not in allowed_territories:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown territory {territory!r}; allowed: {allowed_territories}",
        )

    # Stateless, session-less scratch state — intentionally never saved.
    user_id = user_id + "-system"
    state = AgentState(
        allowed_territories=allowed_territories,
        territory=territory,
        user_id=user_id,
        user_role=user_role,
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
    await _authenticate(authorization)

    from app.utils.token_tacking import get_usage_per_day

    return get_usage_per_day()


# ---------------------------------------------------------------------------
# Operational / health endpoints
# ---------------------------------------------------------------------------
# These endpoints intentionally do not require authentication so that
# Kubernetes/load-balancer probes can call them without credentials.
#
# GET /health       - overall application health
# GET /health/live  - liveness probe: process is alive and serving requests
# GET /health/ready - readiness probe: application dependencies are initialized
#
# Keep these endpoints cheap and side-effect free. They should never invoke
# the agent or perform an expensive backend operation.
@router.get("/health", tags=["health"])
async def health():
    """Return the overall health of the API process."""
    return {
        "status": "ok",
        "service": "api",
    }


@router.get("/health/live", tags=["health"])
async def health_live():
    """Kubernetes/container liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def health_ready():
    """Readiness probe for load balancers/orchestrators.

    The route registry is initialized lazily by the application, so avoid
    forcing initialization here. A successful response means this API process
    is accepting requests; dependency-specific checks can be added here later
    if they become available.
    """
    return {"status": "ready"}


@router.get("/health/version", tags=["health"])
async def health_version():
    """Expose a lightweight service/version identifier for diagnostics."""
    return {
        "service": "api",
        "version": os.environ.get("APP_VERSION", "unknown"),
    }
