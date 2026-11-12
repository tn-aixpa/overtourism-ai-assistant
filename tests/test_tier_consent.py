"""
Tier access consent: the exploitative tier (general_question_response,
web_search) answers from unverified knowledge, so a session must agree to it
once before any such tool runs.

Covers the three moving parts, none of which had tests:
  * CognitiveState.has_valid_tier_consent / grant_tier_consent (+ 24 h TTL)
  * tool_executor_node's gate (pause BEFORE running, bump the answer tier AFTER)
  * wait_user_input_node's handling of the user's yes / no / unclear reply
"""

from datetime import datetime, timedelta

import pytest

from app.agent.nodes import tool_executor as te
from app.agent.nodes import waiting
from app.agent.state import (
    TIER_CONSENT_TTL,
    TIERS_REQUIRING_CONSENT,
    AgentState,
    AgentTier,
)
from app.tools.tool_registry import _ensure_tool_registry


@pytest.fixture
def state() -> AgentState:
    s = AgentState(
        session_id="s", territory="molveno", allowed_territories=["molveno"],
        user_role="editor", session_mode="standalone",
    )
    _ensure_tool_registry()
    return s


@pytest.fixture
def ran(monkeypatch):
    """Record which tools actually executed (instead of running them)."""
    calls = []

    def fake_execute(tool_name, args, state, allow_disabled=False):
        calls.append(tool_name)
        return {"success": True, "output": {"answer": "x", "message": "m"}, "error": None}

    monkeypatch.setattr(te, "execute_selected_tool", fake_execute)
    return calls


def select(state, tool, **args):
    state.cognitive.selected_tool = tool
    state.cognitive.tool_arguments = args
    state.cognitive.pending_thought = "thinking"


# ---------------------------------------------------------------------------
# State: consent bookkeeping
# ---------------------------------------------------------------------------


class TestConsentBookkeeping:
    def test_only_the_exploitative_tier_is_gated(self):
        assert TIERS_REQUIRING_CONSENT == {"exploitative"}

    @pytest.mark.parametrize("tier", ["executor", "operative", "methodological"])
    def test_ungated_tiers_never_need_consent(self, state, tier):
        assert state.cognitive.has_valid_tier_consent(tier) is True

    def test_exploitative_needs_consent_initially(self, state):
        assert state.cognitive.has_valid_tier_consent("exploitative") is False

    def test_granting_consent_unlocks_it(self, state):
        state.cognitive.grant_tier_consent("exploitative")
        assert state.cognitive.has_valid_tier_consent("exploitative") is True

    def test_consent_expires_after_the_ttl(self, state):
        state.cognitive.tier_consent["exploitative"] = (
            datetime.now() - TIER_CONSENT_TTL - timedelta(seconds=1)
        )
        assert state.cognitive.has_valid_tier_consent("exploitative") is False

    def test_consent_just_inside_the_ttl_is_still_valid(self, state):
        state.cognitive.tier_consent["exploitative"] = (
            datetime.now() - TIER_CONSENT_TTL + timedelta(minutes=1)
        )
        assert state.cognitive.has_valid_tier_consent("exploitative") is True


# ---------------------------------------------------------------------------
# Executor gate
# ---------------------------------------------------------------------------


class TestExecutorGate:
    @pytest.mark.parametrize("tool", ["general_question_response", "web_search"])
    def test_exploitative_tool_pauses_for_consent_and_does_not_run(self, state, ran, tool):
        select(state, tool, query="what is carrying capacity?")
        result = te.tool_executor_node(state)
        assert result.goto == "WAIT_USER_INPUT"
        assert state.cognitive.pending_tier_consent == "exploitative"
        assert state.cognitive.tier_consent_resume_goto == "tool_executor"
        assert ran == []
        # the request is kept so it can run once consent is granted
        assert state.cognitive.selected_tool == tool
        assert state.cognitive.tool_arguments == {"query": "what is carrying capacity?"}
        assert state.active_agent == AgentTier.EXECUTOR  # no tier bump before consent

    def test_with_consent_it_runs_and_the_answer_tier_is_exploitative(self, state, ran):
        state.cognitive.grant_tier_consent("exploitative")
        select(state, "general_question_response", query="q")
        result = te.tool_executor_node(state)
        assert result.goto == "react_reasoner"
        assert ran == ["general_question_response"]
        assert state.active_agent == AgentTier.EXPLOITATIVE

    def test_expired_consent_asks_again(self, state, ran):
        state.cognitive.tier_consent["exploitative"] = (
            datetime.now() - TIER_CONSENT_TTL - timedelta(minutes=1)
        )
        select(state, "web_search", query="q")
        assert te.tool_executor_node(state).goto == "WAIT_USER_INPUT"
        assert ran == []

    def test_executor_tier_tools_never_ask_for_consent(self, state, ran):
        select(state, "lookup_glossary", query="overtourism")
        result = te.tool_executor_node(state)
        assert result.goto == "react_reasoner"
        assert state.cognitive.pending_tier_consent is None
        assert ran == ["lookup_glossary"]

    def test_the_answer_tier_only_ever_rises_within_a_turn(self, state, ran):
        state.cognitive.grant_tier_consent("exploitative")
        select(state, "general_question_response", query="q")
        te.tool_executor_node(state)
        select(state, "lookup_glossary", query="overtourism")
        te.tool_executor_node(state)
        assert state.active_agent == AgentTier.EXPLOITATIVE

    def test_operative_tool_lifts_the_tier_above_executor(self, state, ran):
        select(state, "get_system_capabilities")
        te.tool_executor_node(state)
        assert state.active_agent == AgentTier.OPERATIVE


# ---------------------------------------------------------------------------
# Wait node: the user's answer
# ---------------------------------------------------------------------------


@pytest.fixture
def pending(state):
    select(state, "general_question_response", query="q")
    state.cognitive.pending_tier_consent = "exploitative"
    state.cognitive.tier_consent_resume_goto = "tool_executor"
    return state


class TestConsentReply:
    def test_first_visit_asks_the_question_and_waits(self, pending):
        result = waiting.wait_user_input_node(pending)
        assert result.goto == "generate_output_message"
        assert pending.waiting_for == AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        assert "unverified" in pending.cognitive.messages_to_include[0]

    @pytest.mark.parametrize("reply", ["yes", "sì", "ok", "va bene"])
    def test_yes_grants_consent_and_resumes_the_tool(self, pending, reply):
        pending.waiting_for = AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        pending.user_input = reply
        result = waiting.wait_user_input_node(pending)
        assert result.goto == "tool_executor"
        assert pending.cognitive.has_valid_tier_consent("exploitative")
        assert pending.cognitive.pending_tier_consent is None
        assert pending.waiting_for is None and pending.user_input is None
        assert pending.cognitive.selected_tool == "general_question_response"

    @pytest.mark.parametrize("reply", ["no", "no grazie", "annulla", "cancel"])
    def test_no_records_the_refusal_and_hands_back_to_the_reasoner(self, pending, reply):
        pending.waiting_for = AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        pending.user_input = reply
        result = waiting.wait_user_input_node(pending)
        assert result.goto == "react_reasoner"
        assert not pending.cognitive.has_valid_tier_consent("exploitative")
        step = pending.cognitive.scratchpad[-1]
        assert step.status == "tier_access_declined"
        assert step.tool_name == "general_question_response"
        assert step.observation["success"] is False
        assert pending.cognitive.selected_tool is None  # the tool will not run

    # "non voglio" is deliberately NOT a bare refusal: a cancellation word with
    # other content may carry a new request, so it is asked again (harmless
    # for a consent question) instead of being swallowed.
    @pytest.mark.parametrize("reply", ["hmm maybe", "non voglio", "no, prima spiegami meglio"])
    def test_unclear_reply_asks_again_and_keeps_the_request(self, pending, reply):
        pending.waiting_for = AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        pending.user_input = reply
        result = waiting.wait_user_input_node(pending)
        assert result.goto == "generate_output_message"
        assert pending.cognitive.pending_tier_consent == "exploitative"
        assert pending.cognitive.selected_tool == "general_question_response"
        assert not pending.cognitive.has_valid_tier_consent("exploitative")
