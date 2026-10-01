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
