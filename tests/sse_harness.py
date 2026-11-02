"""
Test harness for the SSE / agent-turn lifecycle.

What is real and what is fake
-----------------------------
REAL   : FastAPI routes, uvicorn (so the asyncio event loop behaves like in
         production), events.py (TurnStore / iter_sse), memory.py, _run_agent
         (watchdog, thread hand-off), AgentState.dump_to_file,
         StreamingResponse.
FAKE   : the LangGraph agent (`app.api.routes.agent_app`) is replaced by a
         `ScriptedAgent` that publishes actions exactly like
         tool_executor.py does (via events.publish_action) and then
         "generates" an answer. The backend auth calls (`check_authorization`,
         `get_allowed_territories`) are faked so the tests need neither
         network nor an LLM.

Contract exercised (turn-based API)
-----------------------------------
    POST /agent                        -> 202 {session_id, turn_id}
    GET  /agent/turns/{turn_id}/events -> SSE: `status` events (id: 1, 2, ...)
                                          then exactly one `done`
    GET  /agent/turns/{turn_id}        -> {status, last_event_id, result}

`thought` steps no longer exist: events.publish_thought is a deliberate no-op,
so the only thing a stream ever carries is `{"type": "action", "tool": ...}`.

A real server (rather than TestClient / ASGITransport) is used on purpose:
those in-process transports buffer the whole streaming body, so they can
neither reproduce "the event arrives seconds late" nor event-loop blocking.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
import uvicorn

from app.agent import events, memory
from app.agent.state import AgentState

AUTH = {"Authorization": "Bearer test-token"}


# --------------------------------------------------------------------------- #
# Scripted fake agent
# --------------------------------------------------------------------------- #
@dataclass
class Step:
    kind: str  # action | sleep | raise | hang | call
    value: Any = None
    delay: float = 0.0  # seconds to wait BEFORE executing the step


def action(tool: str, delay: float = 0.0) -> Step:
    return Step("action", tool, delay)


def sleep(seconds: float) -> Step:
    return Step("sleep", seconds)


def raise_(exc: BaseException, delay: float = 0.0) -> Step:
    return Step("raise", exc, delay)


def hang(seconds: float) -> Step:
    """A node stuck on a hung backend/LLM call (finishes eventually)."""
    return Step("hang", seconds)


def call(fn: Callable[[], None], delay: float = 0.0) -> Step:
    return Step("call", fn, delay)


class ScriptedAgent:
    """Drop-in for `agent_app`: only `.invoke(state, config)` is used by routes."""

    def __init__(self, script_for: Callable[[str, str], list[Step]] | None = None):
        # script_for(session_id, user_message) -> steps
        self.script_for = script_for or (lambda sid, msg: [action("tool")])
        self.invocations: list[dict] = []
        self._lock = threading.Lock()
        self.on_invoke_returned: Callable[[str, float], None] | None = None

    def invoke(self, state, config=None):
        sid = state.session_id
        last_user = state.get_last_message().content
        with self._lock:
            self.invocations.append({"session": sid, "t": time.monotonic()})

        for step in self.script_for(sid, last_user):
            if step.delay:
                time.sleep(step.delay)
            if step.kind == "action":
                events.publish_action(sid, step.value)
            elif step.kind in ("sleep", "hang"):
                time.sleep(step.value)
            elif step.kind == "raise":
                raise step.value
            elif step.kind == "call":
                step.value()

        state.add_assistant_message(f"answer-to:{last_user}")
        t_ret = time.monotonic()
        if self.on_invoke_returned:
            self.on_invoke_returned(sid, t_ret)
        return dict(state.__dict__)


# --------------------------------------------------------------------------- #
# Real uvicorn server in a thread
# --------------------------------------------------------------------------- #
class LiveServer:
    def __init__(self, app):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        self.config = uvicorn.Config(
            app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="off"
        )
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.02)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# SSE client that behaves like the frontend
# --------------------------------------------------------------------------- #
@dataclass
class TurnRecord:
    session: str
    message: str
    turn_id: str | None = None
    post_status: int | None = None
    t_post: float = 0.0
    t_post_returned: float = 0.0
    sse_events: list[tuple[float, str, str]] = field(default_factory=list)  # (t, name, data)
    t_done: float | None = None
    t_result: float | None = None
    result_status: int | None = None
    result: dict | None = None
    error: str | None = None
    stream_closed_without_done: bool = False

    @property
    def statuses(self) -> list[dict]:
        return [json.loads(d) for _, n, d in self.sse_events if n == "status"]

    @property
    def tools(self) -> list[str]:
        """Tool names of the `action` events, in stream order."""
        return [s["tool"] for s in self.statuses if s["type"] == "action"]

    @property
    def done_payload(self) -> dict | None:
        for _, n, d in self.sse_events:
            if n == "done":
                return json.loads(d)
        return None

    @property
    def got_done(self) -> bool:
        return self.t_done is not None


_EOL = re.compile(r"\r\n|\n|\r")


def sse_lines(response):
    """Split a streaming httpx response into lines the way the SSE spec (and
    browsers' EventSource) does: ONLY on CR, LF or CRLF. httpx's iter_lines()
    follows str.splitlines() and would also split on U+2028/U+2029/U+0085."""
    buf = ""
    for chunk in response.iter_text():
        buf += chunk
        parts = _EOL.split(buf)
        # a trailing "\r" may be the first half of a "\r\n" split across chunks
        if buf.endswith("\r"):
            buf_tail, parts = "\r", _EOL.split(buf[:-1])
            buf = buf_tail
            tail = parts.pop() if parts else ""
            # re-join: the incomplete last line stays buffered with its CR
            for line in parts:
                yield line
            buf = tail + "\r"
            continue
        buf = parts.pop()
        for line in parts:
            yield line
    if buf:
        yield buf


def parse_sse_frames(lines):
    """Yield (event_id, event_name, data) from an iterator of text lines (SSE
    spec subset). `event_id` is None for frames without an `id:` field."""
    name, data, event_id = "message", [], None
    for line in lines:
        if line == "":
            if data or name != "message":
                yield event_id, name, "\n".join(data)
            name, data, event_id = "message", [], None
        elif line.startswith(":"):
            continue  # comment / keep-alive
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif line.startswith("id:"):
            event_id = int(line[3:].strip())


def parse_sse_lines(lines):
    """Yield (event_name, data) - same as parse_sse_frames without the id."""
    for _id, name, data in parse_sse_frames(lines):
        yield name, data


# --------------------------------------------------------------------------- #
# Small HTTP helpers shared by the tests
# --------------------------------------------------------------------------- #
def auth_for(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def seed_session(session: str, user_id: str = "user-1", **state_kwargs) -> AgentState:
    """Put a session straight into the in-memory store (skips /agent/init)."""
    state = memory.load_state(session)
    if state is None:
        state = AgentState(
            session_id=session,
            user_id=user_id,
            allowed_territories=["test-territory"],
            territory="test-territory",
            **state_kwargs,
        )
        memory.remember_state(state)
    return state


def post_turn(
    base: str,
    session: str,
    message: str = "hi",
    *,
    headers: dict | None = None,
    seed: bool = True,
    **form,
) -> httpx.Response:
    """POST /agent. Seeds the session first unless seed=False."""
    if seed:
        seed_session(session)
    with httpx.Client(base_url=base, timeout=10) as c:
        return c.post(
            "/agent",
            data={"message": message, "session_id": session, **form},
            headers=headers if headers is not None else AUTH,
        )


def read_stream(
    base: str,
    turn_id: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    timeout: float = 20.0,
) -> list[tuple[int | None, str, str]]:
    """Open the turn's event stream, read it to the end, return the frames."""
    with httpx.Client(base_url=base, timeout=timeout) as c:
        with c.stream(
            "GET",
            f"/agent/turns/{turn_id}/events",
            headers=AUTH if headers is None else headers,
            params=params,
        ) as r:
            assert r.status_code == 200, r.status_code
            return list(parse_sse_frames(sse_lines(r)))


def get_turn(base: str, turn_id: str, headers: dict | None = None) -> httpx.Response:
    with httpx.Client(base_url=base, timeout=10) as c:
        return c.get(
            f"/agent/turns/{turn_id}", headers=AUTH if headers is None else headers
        )


def wait_for_status(base: str, turn_id: str, *, timeout: float = 10.0) -> dict:
    """Poll GET /agent/turns/{id} until it is terminal (the polling fallback)."""
    deadline = time.time() + timeout
    while True:
        body = get_turn(base, turn_id).json()
        if body["status"] != "running" or time.time() > deadline:
            return body
        time.sleep(0.02)


def run_turn(
    base: str,
    session: str,
    message: str,
    *,
    read_timeout: float = 20.0,
    fetch_result: bool = True,
    stream_headers: dict | None = None,
    extra_form: dict | None = None,
    post_headers: dict | None = None,
) -> TurnRecord:
    """POST /agent -> stream this turn's events -> retrieve its result."""
    seed_session(session)

    rec = TurnRecord(session=session, message=message)
    try:
        with httpx.Client(base_url=base, timeout=httpx.Timeout(read_timeout)) as c:
            rec.t_post = time.monotonic()
            r = c.post(
                "/agent",
                data={"message": message, "session_id": session, **(extra_form or {})},
                headers=post_headers or AUTH,
            )
            rec.t_post_returned = time.monotonic()
            rec.post_status = r.status_code
            if r.status_code != 202:
                rec.error = f"POST /agent -> {r.status_code} {r.text}"
                return rec
            rec.turn_id = r.json()["turn_id"]

            with c.stream(
                "GET",
                f"/agent/turns/{rec.turn_id}/events",
                headers=stream_headers or AUTH,
            ) as s:
                if s.status_code != 200:
                    rec.error = f"stream -> {s.status_code}"
                    return rec
                for name, data in parse_sse_lines(sse_lines(s)):
                    now = time.monotonic()
                    rec.sse_events.append((now, name, data))
                    if name == "done":
                        rec.t_done = now
                        break
                else:
                    rec.stream_closed_without_done = True

            if fetch_result and rec.got_done:
                rr = c.get(f"/agent/turns/{rec.turn_id}", headers=AUTH)
                rec.t_result = time.monotonic()
                rec.result_status = rr.status_code
                rec.result = rr.json().get("result") if rr.status_code == 200 else None
    except httpx.TimeoutException as e:
        rec.error = f"timeout: {type(e).__name__}"
    except Exception as e:  # noqa: BLE001
        rec.error = f"{type(e).__name__}: {e}"
    return rec
