"""
Test harness for the SSE / agent-turn lifecycle.

What is real and what is fake
-----------------------------
REAL   : FastAPI routes, uvicorn (so the asyncio event loop behaves like in
         production), events.py, memory.py, _run_agent (watchdog, thread
         hand-off), AgentState.dump_to_file, StreamingResponse.
FAKE   : the LangGraph agent (`app.api.routes.agent_app`) is replaced by a
         `ScriptedAgent` that publishes thoughts/actions exactly like
         reasoner.py / tool_executor.py do (via events.publish_thought /
         publish_action) and then "generates" an answer. The backend auth
         calls (`check_authorization`, `get_allowed_territories`) are faked so
         the tests need neither network nor an LLM.

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

from app.agent import events

AUTH = {"Authorization": "Bearer test-token"}


# --------------------------------------------------------------------------- #
# Scripted fake agent
# --------------------------------------------------------------------------- #
@dataclass
class Step:
    kind: str  # thought | action | sleep | raise | hang | call
    value: Any = None
    delay: float = 0.0  # seconds to wait BEFORE executing the step


def thought(text: str, delay: float = 0.0) -> Step:
    return Step("thought", text, delay)


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
        self.script_for = script_for or (lambda sid, msg: [thought("t"), action("tool")])
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
            if step.kind == "thought":
                events.publish_thought(sid, step.value)
            elif step.kind == "action":
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


def parse_sse_lines(lines):
    """Yield (event_name, data) from an iterator of text lines (SSE spec subset)."""
    name, data = "message", []
    for line in lines:
        if line == "":
            if data or name != "message":
                yield name, "\n".join(data)
            name, data = "message", []
        elif line.startswith(":"):
            continue  # comment / keep-alive
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))


def run_turn(
    base: str,
    session: str,
    message: str,
    *,
    read_timeout: float = 20.0,
    fetch_result: bool = True,
    stream_headers: dict | None = None,
    extra_form: dict | None = None,
) -> TurnRecord:
    """POST /agent -> GET /agent/stream -> (on done) GET /agent/result."""
    rec = TurnRecord(session=session, message=message)
    try:
        with httpx.Client(base_url=base, timeout=httpx.Timeout(read_timeout)) as c:
            rec.t_post = time.monotonic()
            r = c.post(
                "/agent",
                data={"message": message, "session_id": session, **(extra_form or {})},
                headers=AUTH,
            )
            rec.t_post_returned = time.monotonic()
            rec.post_status = r.status_code
            if r.status_code != 202:
                rec.error = f"POST /agent -> {r.status_code} {r.text}"
                return rec

            with c.stream(
                "GET", f"/agent/stream/{session}", headers=stream_headers or AUTH
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
                rr = c.get(f"/agent/result/{session}", headers=AUTH)
                rec.t_result = time.monotonic()
                rec.result_status = rr.status_code
                rec.result = rr.json() if rr.status_code == 200 else None
    except httpx.TimeoutException as e:
        rec.error = f"timeout: {type(e).__name__}"
    except Exception as e:  # noqa: BLE001
        rec.error = f"{type(e).__name__}: {e}"
    return rec
