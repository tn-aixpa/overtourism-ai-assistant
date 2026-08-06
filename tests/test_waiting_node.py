import pytest
from langgraph.types import Command

from app.agent.nodes.waiting import (
    _is_cancellation,
    _is_confirmation,
    _normalize,
    _wait_instructions,
    wait_user_input_node,
)
from app.agent.state import AgentState

# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercases_and_strips_punctuation(self):
        assert _normalize("Yes, go ahead!") == "yes  go ahead"

    def test_strips_surrounding_whitespace(self):
        assert _normalize("   ok   ") == "ok"

    def test_empty_string(self):
        assert _normalize("") == ""

    def test_apostrophe_becomes_space(self):
        assert _normalize("d'accord") == "d accord"


# ---------------------------------------------------------------------------
# _is_confirmation / _is_cancellation
# ---------------------------------------------------------------------------


class TestIsConfirmation:
    @pytest.mark.parametrize(
        "text",
        [
            "yes",
            "Yes",
            "YES!",
            "ok",
            "okay",
            "sure",
            "proceed",
            "go ahead",
            "confirm",
            "correct",
            "fine",
            "agreed",
            "sounds good",
            "sì",
            "si",
            "va bene",
            "d'accord",
            "procedi",
        ],
    )
    def test_exact_confirmatory_phrases(self, text):
        assert _is_confirmation(text) is True

    def test_confirmatory_phrase_embedded_in_longer_sentence(self):
        assert _is_confirmation("Yes, go ahead please") is True
        assert _is_confirmation("sure, sounds good to me") is True

    def test_empty_input_is_not_confirmation(self):
        assert _is_confirmation("") is False
        assert _is_confirmation("   ") is False

    def test_unrelated_text_is_not_confirmation(self):
        assert _is_confirmation("what does this do?") is False

    def test_substring_false_positive_guard(self):
        """'nostalgic' contains 'no' as a substring but must not match the
        cancellation phrase 'no' (word-boundary check), and must not be
        mistaken for a confirmation either."""
        assert _is_cancellation("I feel nostalgic about this") is False
        assert _is_confirmation("I feel nostalgic about this") is False

    def test_cancellation_wins_when_both_present(self):
        assert _is_confirmation("no, not sure") is False
        assert _is_cancellation("no, not sure") is True

    def test_case_insensitive(self):
        assert _is_confirmation("CONFIRM") is True


class TestIsCancellation:
    @pytest.mark.parametrize(
        "text",
        [
            "no",
            "No",
            "cancel",
            "stop",
            "abort",
            "nevermind",
            "never mind",
            "annulla",
            "nein",
        ],
    )
    def test_exact_cancellation_phrases(self, text):
        assert _is_cancellation(text) is True

    def test_cancellation_phrase_embedded_in_sentence(self):
        assert _is_cancellation("no, please cancel this") is True

    def test_empty_input_is_not_cancellation(self):
        assert _is_cancellation("") is False

    def test_unrelated_text_is_not_cancellation(self):
        assert _is_cancellation("please continue") is False


# ---------------------------------------------------------------------------
# _wait_instructions
# ---------------------------------------------------------------------------


class TestWaitInstructions:
    def test_creation_tool_recaps_fields(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {
            "name": "Overtourism",
            "description": "Too many tourists",
            "objective": None,
        }
        msg = _wait_instructions(fresh_state)
        assert "Name: Overtourism" in msg
        assert "Description: Too many tourists" in msg
        assert "Objective" not in msg  # None values are skipped
        assert "Shall I proceed?" in msg

    def test_creation_tool_with_no_fields(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_proposal"
        fresh_state.cognitive.tool_arguments = {}
        msg = _wait_instructions(fresh_state)
        assert "no additional data provided" in msg

    def test_non_creation_tool_generic_message(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "delete_problem"
        fresh_state.cognitive.tool_arguments = {"problem_id": "123"}
        msg = _wait_instructions(fresh_state)
        assert msg == "Please confirm to proceed."

    def test_field_labels_are_humanized(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_scenario"
        fresh_state.cognitive.tool_arguments = {"proposal_id": "p1"}
        msg = _wait_instructions(fresh_state)
        assert "Proposal id: p1" in msg

    def test_empty_string_values_are_skipped(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {"name": "N", "description": ""}
        msg = _wait_instructions(fresh_state)
        assert "Name: N" in msg
        assert "Description" not in msg


# ---------------------------------------------------------------------------
# wait_user_input_node
# ---------------------------------------------------------------------------


class TestWaitUserInputNode:
    def test_first_pass_no_user_input_sets_prompt_and_waiting_for(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {"name": "N", "description": "D"}
        fresh_state.user_input = None

        result = wait_user_input_node(fresh_state)

        assert isinstance(result, Command)
        assert result.goto == "generate_output_message"
        assert fresh_state.waiting_for == AgentState.WaitingFor.PROBLEM_CONFIRMATION
        assert len(fresh_state.cognitive.messages_to_include) == 1
        assert "Shall I proceed?" in fresh_state.cognitive.messages_to_include[0]

    def test_first_pass_unknown_tool_defaults_to_context_input(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.selected_tool = "some_other_tool"
        fresh_state.user_input = None

        wait_user_input_node(fresh_state)

        assert fresh_state.waiting_for == AgentState.WaitingFor.CONTEXT_INPUT

    def test_user_cancels_clears_pending_action(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {"name": "N"}
        fresh_state.cognitive.tool_confirmation_needed = True
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = "no, cancel that"

        result = wait_user_input_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.selected_tool is None
        assert fresh_state.cognitive.tool_arguments == {}
        assert fresh_state.cognitive.tool_confirmation_needed is False
        assert fresh_state.cognitive.tool_confirmed is False
        assert fresh_state.waiting_for is None
        assert fresh_state.user_input is None
        assert "won't submit" in fresh_state.cognitive.messages_to_include[0]

    def test_user_confirms_routes_to_tool_executor(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_confirmation_needed = True
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = "yes"

        result = wait_user_input_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.tool_confirmed is True
        assert fresh_state.cognitive.tool_confirmation_needed is False
        assert fresh_state.waiting_for is None
        assert fresh_state.user_input is None
        # The pending tool itself is preserved so tool_executor can run it.
        assert fresh_state.cognitive.selected_tool == "create_new_problem"

    def test_ambiguous_reply_asks_for_clarification_and_keeps_pending_action(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {"name": "N"}
        fresh_state.cognitive.tool_confirmation_needed = True
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = "actually, let's talk about something else"

        result = wait_user_input_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.selected_tool == "create_new_problem"
        assert fresh_state.cognitive.tool_arguments == {"name": "N"}
        assert fresh_state.waiting_for == AgentState.WaitingFor.PROBLEM_CONFIRMATION
        assert fresh_state.cognitive.tool_confirmation_needed is True
        assert any(
            word in fresh_state.cognitive.messages_to_include[0].lower()
            for word in ("clarify", "clear", "please", "reply")
        )

    def test_user_input_stripped_of_whitespace(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = "   yes   "

        result = wait_user_input_node(fresh_state)

        assert result.goto == "tool_executor"
