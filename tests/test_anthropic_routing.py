"""
Real-model evals.

Unlike test_reasoner_routing.py, these make REAL Anthropic API calls (no
mocking of react_step/llm_interaction) and check that the model's tool
selection matches expectations for realistic user messages.

These are inherently non-deterministic and should NOT run in normal CI /
`pytest` runs — they're skipped unless ANTHROPIC_API_KEY_TEST is set, e.g.:

    ANTHROPIC_API_KEY_TEST=sk-ant-... pytest tests/test_reasoner_eval.py -v

Consider running each case multiple times (see `test_repeat_stability`)
before treating a single failure as a regression — LLM tool selection can be
flaky on ambiguous phrasing even when the prompt is working correctly.
"""

import os

import pytest

from app.agent.nodes.reasoner import initialize_tools, react_reasoner_node
from app.agent.state import AgentState

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY_TEST"),
    reason=(
        "requires a real Anthropic API key in ANTHROPIC_API_KEY_TEST "
        "(kept separate from ANTHROPIC_API_KEY so normal test runs never "
        "accidentally hit the live API)"
    ),
)


@pytest.fixture(autouse=True)
def _use_real_api_key(monkeypatch):
    """These tests need the real Anthropic client, so point
    ANTHROPIC_API_KEY (what app.utils.llm actually reads) at the real key
    for the duration of this module only."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY_TEST"])
    # Force a fresh client so it picks up the real key rather than reusing
    # a cached one built from the fake test key.
    from app.utils import llm as llm_module

    monkeypatch.setattr(llm_module, "_llm_client", None)


def make_state(user_message: str) -> AgentState:
    state = AgentState(session_id="eval-session", tenant="molveno")
    state.add_user_message(user_message)
    return state


def run_one_reasoning_step(user_message: str) -> AgentState:
    """Runs initialize_tools -> react_reasoner_node once (registers the
    real tool set, no mocking) and returns the resulting state."""
    state = make_state(user_message)
    initialize_tools(state)
    react_reasoner_node(state)
    return state


# ---------------------------------------------------------------------------
# Golden dataset: (user message, expected tool, [acceptable alternates])
# ---------------------------------------------------------------------------
# Keep `acceptable_alternates` short and deliberate — it should capture
# genuinely equivalent choices (e.g. the model checking glossary before
# committing to a creation flow), not become a dumping ground that hides
# real regressions.

GOLDEN_CASES = [
    pytest.param(
        "What problems are currently registered in the system?",
        "list_available_problems",
        [],
        id="list_problems",
    ),
    pytest.param(
        "What does 'overtourism' mean on this platform?",
        "lookup_glossary",
        [],
        id="glossary_lookup",
    ),
    pytest.param(
        "What can this system do?",
        "get_system_capabilities",
        [],
        id="system_capabilities",
    ),
    pytest.param(
        "I'd like to register a new problem about traffic congestion downtown.",
        "create_new_problem",
        [],
        id="create_problem",
    ),
    pytest.param(
        "Show me all the proposals we have so far.",
        "list_available_proposals",
        [],
        id="list_proposals",
    ),
    pytest.param(
        "What's a 'scenario' versus a 'proposal' here — are they the same thing?",
        "lookup_glossary",
        [],
        id="glossary_disambiguation",
    ),
]


class TestGoldenToolSelection:
    @pytest.mark.parametrize(
        "user_message,expected_tool,acceptable_alternates", GOLDEN_CASES
    )
    def test_selects_expected_tool(
        self, user_message, expected_tool, acceptable_alternates
    ):
        state = run_one_reasoning_step(user_message)
        selected = state.cognitive.selected_tool
        acceptable = {expected_tool, *acceptable_alternates}

        assert selected in acceptable, (
            f"For input {user_message!r}: expected one of {acceptable}, "
            f"got {selected!r}. Last thought: "
            f"{state.cognitive.trace.steps[-1].data.get('thought') if state.cognitive.trace.steps else None!r}"
        )


class TestNegativeCases:
    """Requests that should NOT trigger a write/creation tool, since those
    require an explicit confirmation step and must never be auto-selected
    from an ambiguous or purely informational message."""

    @pytest.mark.parametrize(
        "user_message",
        [
            "Tell me more about how proposals work.",
            "What would happen if I created a problem about noise pollution?",  # hypothetical, not a request
        ],
    )
    def test_does_not_select_write_tools_for_informational_requests(self, user_message):
        state = run_one_reasoning_step(user_message)
        write_tools = {
            "create_new_problem",
            "create_new_proposal",
            "create_new_scenario",
            "edit_problem",
            "edit_proposal",
            "edit_scenario",
            "delete_problem",
            "delete_proposal",
            "delete_scenario",
        }
        assert state.cognitive.selected_tool not in write_tools


class TestRepeatStability:
    """Tool selection for a clear-cut request should be stable across
    repeated calls, not a coin flip. Run a single unambiguous case N times
    and require a strong majority — a good smoke test for prompt drift
    after editing react_reasoning.py."""

    N_RUNS = 5
    MIN_PASS_RATE = 0.8

    def test_repeat_stability_on_unambiguous_request(self):
        user_message = "What does 'overtourism' mean?"
        expected_tool = "lookup_glossary"

        outcomes = [
            run_one_reasoning_step(user_message).cognitive.selected_tool
            for _ in range(self.N_RUNS)
        ]
        pass_rate = outcomes.count(expected_tool) / self.N_RUNS

        assert pass_rate >= self.MIN_PASS_RATE, (
            f"Only {pass_rate:.0%} of {self.N_RUNS} runs selected "
            f"'{expected_tool}' for {user_message!r}. Outcomes: {outcomes}"
        )
