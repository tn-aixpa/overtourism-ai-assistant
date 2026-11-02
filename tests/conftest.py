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
# API fixtures for the route / SSE / turn-lifecycle tests (see sse_harness.py)
# ---------------------------------------------------------------------------
@pytest.fixture
def api_env(monkeypatch, tmp_path):
    """
    The real FastAPI routes + events + memory, wired to a ScriptedAgent and
    faked backend calls. Nothing is served yet: `live` serves `.app` over real
    HTTP (uvicorn), `client` drives it in-process with TestClient.

    Namespace:
      .app / .routes / .store / .agent   - the pieces under test
      .users                             - token -> user_id (default "user-1")
      .role                              - role every faked token gets
      .authorized                        - set False to make the backend reject
      .auth_calls                        - list of tokens check_authorization saw
      .territories                       - what get_allowed_territories returns
      .auth_delay / .territories_delay   - seconds of *blocking* sleep, like the
                                           sync `requests` calls in production
    """
    import time
    import types

    from fastapi import FastAPI

    import sse_harness as h
    from app.agent import events, memory
    from app.api import routes

    # state dumps (logs/state_<sid>.json) must not pollute the repo
    monkeypatch.chdir(tmp_path)

    ns = types.SimpleNamespace(
        auth_delay=0.0,
        territories_delay=0.0,
        users={},
        role="viewer",
        authorized=True,
        auth_calls=[],
        territories=["test-territory"],
    )

    def fake_check_authorization(token):
        ns.auth_calls.append(token)
        if ns.auth_delay:
            time.sleep(ns.auth_delay)  # blocking, like requests.get
        return ns.authorized, ns.role, ns.users.get(token, "user-1")

    def fake_territories(token=None):
        if ns.territories_delay:
            time.sleep(ns.territories_delay)
        return list(ns.territories)

    agent = h.ScriptedAgent()
    monkeypatch.setattr(routes, "check_authorization", fake_check_authorization)
    monkeypatch.setattr(routes, "get_allowed_territories", fake_territories)
    monkeypatch.setattr(routes, "set_token", lambda t: None)
    monkeypatch.setattr(routes, "agent_app", agent)
    monkeypatch.setattr(routes, "AUTH_ENABLED", True)
    monkeypatch.setattr(routes, "AGENT_TURN_TIMEOUT", 30.0)
    # the 30 s token cache is process-wide: isolate it per test
    monkeypatch.setattr(routes, "_AUTH_CACHE", {})

    # Isolate the per-turn event store and state singletons.
    monkeypatch.setattr(events, "store", events.TurnStore())
    monkeypatch.setattr(routes, "store", events.store)
    for d in (memory._STATE_STORE, memory._LOCKS):
        d.clear()

    app = FastAPI()
    app.include_router(routes.router)

    ns.app = app
    ns.agent = agent
    ns.routes = routes
    ns.store = events.store
    try:
        yield ns
    finally:
        for d in (memory._STATE_STORE, memory._LOCKS):
            d.clear()


@pytest.fixture
def live(api_env):
    """`api_env` served by a real uvicorn server (needed for streaming/timing
    tests: in-process transports buffer the whole body). Adds `.base`."""
    import sse_harness as h

    server = h.LiveServer(api_env.app)
    server.start()
    api_env.base = server.base
    api_env.server = server
    try:
        yield api_env
    finally:
        server.stop()


@pytest.fixture
def client(api_env):
    """In-process TestClient. Background work (the agent turn) has finished by
    the time a POST /agent returns, which makes route tests deterministic."""
    from fastapi.testclient import TestClient

    with TestClient(api_env.app) as c:
        api_env.client = c
        yield c
