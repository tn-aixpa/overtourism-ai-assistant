"""
Shared pytest fixtures.

Required env vars (BACKEND_URL, ANTHROPIC_API_KEY) are set here, at session
start, before anything under `app` is imported — several modules
(app.tools.backend_tools) read them at import time.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("BACKEND_URL", "http://backend.test/")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.agent.state import AgentState
from app.tools import tool_registry as tool_registry_module


@pytest.fixture(autouse=True)
def _reset_tool_registry():
    """The tool registry is a process-wide singleton (get_tool_registry()).
    Reset it before/after every test so tests can't leak tool registrations
    into one another regardless of execution order."""
    tool_registry_module.reset_tool_registry()
    yield
    tool_registry_module.reset_tool_registry()


@pytest.fixture
def fresh_state() -> AgentState:
    """A minimal, valid AgentState for a new session."""
    return AgentState(session_id="test-session", territory="test-territory")


# ---------------------------------------------------------------------------
# Live-server fixtures for the SSE / turn-lifecycle tests (see sse_harness.py)
# ---------------------------------------------------------------------------
@pytest.fixture
def live(monkeypatch, tmp_path):
    """
    A real uvicorn server running the real FastAPI routes, with the LangGraph
    agent replaced by a ScriptedAgent and the backend auth calls faked.

    Yields a namespace: .base (URL), .agent (ScriptedAgent), .routes (module),
    .auth_delay / .territories_delay (settable seconds of *blocking* sleep,
    emulating a slow backend, exactly like the sync `requests` calls do).
    """
    import time
    import types

    from fastapi import FastAPI

    import sse_harness as h
    from app.agent import events, memory
    from app.api import routes

    # state dumps (logs/state_<sid>.json) must not pollute the repo
    monkeypatch.chdir(tmp_path)

    ns = types.SimpleNamespace(auth_delay=0.0, territories_delay=0.0)

    def fake_check_authorization(token):
        if ns.auth_delay:
            time.sleep(ns.auth_delay)  # blocking, like requests.get
        return True, "viewer", "user-1"

    def fake_territories(token=None):
        if ns.territories_delay:
            time.sleep(ns.territories_delay)
        return ["test-territory"]

    agent = h.ScriptedAgent()
    monkeypatch.setattr(routes, "check_authorization", fake_check_authorization)
    monkeypatch.setattr(routes, "get_allowed_territories", fake_territories)
    monkeypatch.setattr(routes, "set_token", lambda t: None)
    monkeypatch.setattr(routes, "agent_app", agent)
    monkeypatch.setattr(routes, "AUTH_ENABLED", True)
    monkeypatch.setattr(routes, "AGENT_TURN_TIMEOUT", 30.0)

    # isolate process-wide singletons
    for d in (events._queues, events._results, memory._STATE_STORE, memory._LOCKS):
        d.clear()
    memory._IN_FLIGHT.clear()

    app = FastAPI()
    app.include_router(routes.router)
    server = h.LiveServer(app)
    server.start()

    ns.base = server.base
    ns.agent = agent
    ns.routes = routes
    ns.server = server
    try:
        yield ns
    finally:
        server.stop()
        for d in (events._queues, events._results, memory._STATE_STORE, memory._LOCKS):
            d.clear()
        memory._IN_FLIGHT.clear()
