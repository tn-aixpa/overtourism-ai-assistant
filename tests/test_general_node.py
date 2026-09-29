import os
from unittest.mock import patch

import pytest
from langgraph.graph import END
from langgraph.types import Command

from app.agent.nodes import general as gn
from app.agent.state import AgentState, ReActStep

# ---------------------------------------------------------------------------
# _build_messages_from_tool_result
# ---------------------------------------------------------------------------


class TestBuildMessagesFromToolResult:
    def test_failed_result_returns_error_message(self):
        result = {"success": False, "error": "boom"}
        msgs = gn._build_messages_from_tool_result("list_available_problems", result)
        assert msgs == ["The operation failed: boom"]

    def test_failed_result_without_explicit_error_uses_fallback(self):
        result = {"success": False}
        msgs = gn._build_messages_from_tool_result("list_available_problems", result)
        assert msgs == ["The operation failed: An unknown error occurred."]

    def test_get_system_capabilities(self):
        result = {"success": True, "output": {"system_description": "System does X"}}
        msgs = gn._build_messages_from_tool_result("get_system_capabilities", result)
        assert msgs == ["System does X"]

    def test_get_system_capabilities_missing_description(self):
        result = {"success": True, "output": {}}
        msgs = gn._build_messages_from_tool_result("get_system_capabilities", result)
        assert msgs == ["System description unavailable."]

    @pytest.mark.parametrize(
        "tool_name",
        [
            "list_available_problems",
            "list_available_proposals",
            "list_available_scenarios",
        ],
    )
    def test_list_tools_include_output(self, tool_name):
        result = {"success": True, "output": {"items": [1, 2, 3]}}
        msgs = gn._build_messages_from_tool_result(tool_name, result)
        assert "Here are the available items" in msgs[0]

    def test_get_context_details(self):
        result = {"success": True, "output": {"retrieved": {"problems 1": {}}}}
        msgs = gn._build_messages_from_tool_result("get_context_details", result)
        assert "Here are the requested details" in msgs[0]

    def test_analyze_scenario_results_returns_message(self):
        result = {"success": True, "output": {"message": "The answer is 42."}}
        msgs = gn._build_messages_from_tool_result("analyze_scenario_results", result)
        assert msgs == ["The answer is 42."]

    def test_analyze_scenario_results_missing_message_fallback(self):
        result = {"success": True, "output": {}}
        msgs = gn._build_messages_from_tool_result("analyze_scenario_results", result)
        assert msgs == ["No answer could be generated."]

    @pytest.mark.parametrize("tool_name", ["create_new_problem", "create_new_proposal"])
    def test_create_success_message(self, tool_name):
        result = {"success": True, "output": {"name": "Overtourism"}}
        msgs = gn._build_messages_from_tool_result(tool_name, result)
        assert "was created successfully" in msgs[0]

    def test_create_success_message_missing_name_fallback(self):
        result = {"success": True, "output": {}}
        msgs = gn._build_messages_from_tool_result("create_new_problem", result)
        assert "was created successfully" in msgs[0]

    @pytest.mark.parametrize(
        "tool_name", ["edit_problem", "edit_proposal", "edit_scenario"]
    )
    def test_edit_success_message(self, tool_name):
        result = {"success": True, "output": {"name": "Overtourism"}}
        msgs = gn._build_messages_from_tool_result(tool_name, result)
        assert "was modified successfully" in msgs[0]

    @pytest.mark.parametrize(
        "tool_name", ["delete_problem", "delete_proposal", "delete_scenario"]
    )
    def test_delete_success_message(self, tool_name):
        result = {"success": True, "output": {"name": "Overtourism"}}
        msgs = gn._build_messages_from_tool_result(tool_name, result)
        assert "was deleted successfully" in msgs[0]

    def test_lookup_glossary_with_matches(self):
        result = {
            "success": True,
            "output": {
                "matches": [
                    {
                        "term": "problem",
                        "definition": "A critical situation.",
                        "aliases": ["issue"],
                        "related_terms": ["proposal"],
                        "examples": ["Overtourism"],
                    }
                ]
            },
        }
        msgs = gn._build_messages_from_tool_result("lookup_glossary", result)
        assert len(msgs) == 1
        text = msgs[0]
        assert "**Problem**: A critical situation." in text
        assert "Also known as: issue" in text
        assert "Related: proposal" in text
        assert "Examples: Overtourism" in text

    def test_lookup_glossary_no_matches(self):
        result = {
            "success": True,
            "output": {"matches": [], "message": "No entries found."},
        }
        msgs = gn._build_messages_from_tool_result("lookup_glossary", result)
        assert msgs == ["No entries found."]

    def test_unknown_tool_falls_back_to_str_output(self):
        result = {"success": True, "output": {"foo": "bar"}}
        msgs = gn._build_messages_from_tool_result("some_unknown_tool", result)
        assert msgs == [str({"foo": "bar"})]

    def test_output_none_is_treated_as_empty_dict(self):
        result = {"success": True, "output": None}
        msgs = gn._build_messages_from_tool_result("create_new_problem", result)
        assert "was created successfully" in msgs[0]

    def test_output_key_absent_falls_back_to_whole_result(self):
        # Some tool results (e.g. execute_lookup_glossary's raw dict) don't
        # wrap their payload under "output" at all.
        result = {"success": True, "matches": []}
        msgs = gn._build_messages_from_tool_result("lookup_glossary", result)
        assert msgs == [result.get("message", "No glossary entries found.")]


# ---------------------------------------------------------------------------
# safe()
# ---------------------------------------------------------------------------


class TestSafeWrapper:
    def test_successful_node_passes_through(self, fresh_state: AgentState):
        def node_fn(state):
            return "ok"

        wrapped = gn.safe(node_fn, "my_node")
        assert wrapped(fresh_state) == "ok"

    def test_exception_is_caught_and_routes_to_error(self, fresh_state: AgentState):
        def node_fn(state):
            raise ValueError("kaboom")

        wrapped = gn.safe(node_fn, "my_node")
        result = wrapped(fresh_state)

        assert isinstance(result, Command)
        assert result.goto == "error"
        assert "kaboom" in fresh_state.cognitive.error_details
        assert "my_node" in fresh_state.cognitive.error_details

    def test_graph_interrupt_is_reraised(self, fresh_state: AgentState):
        from langgraph.errors import GraphInterrupt

        def node_fn(state):
            raise GraphInterrupt("interrupt!")

        wrapped = gn.safe(node_fn, "my_node")
        with pytest.raises(GraphInterrupt):
            wrapped(fresh_state)


# ---------------------------------------------------------------------------
# error_recovery_node
# ---------------------------------------------------------------------------


class TestErrorRecoveryNode:
    def test_writes_error_details_to_log_file(self, fresh_state: AgentState, tmp_path):
        fresh_state.cognitive.error_details = "something bad happened"

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            os.makedirs("logs", exist_ok=True)
            result = gn.error_recovery_node(fresh_state)
            with open("logs/errors.txt") as f:
                content = f.read()
        finally:
            os.chdir(cwd)

        assert "something bad happened" in content
        assert result.goto == "generate_output_message"

    def test_no_error_details_skips_log_write(self, fresh_state: AgentState, tmp_path):
        fresh_state.cognitive.error_details = ""
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            gn.error_recovery_node(fresh_state)
            assert not os.path.exists("logs/errors.txt")
        finally:
            os.chdir(cwd)


# ---------------------------------------------------------------------------
# generate_output_message_node
# ---------------------------------------------------------------------------


class TestGenerateOutputMessageNode:
    def test_builds_messages_from_scratchpad_when_none_prepared(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.tool_results["lookup_glossary"] = {
            "success": True,
            "output": {"matches": [], "message": "No entries found."},
        }
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name="lookup_glossary", observation_key="lookup_glossary")
        ]

        with patch.object(
            gn, "generate_answer", return_value="Final answer"
        ) as mock_gen:
            result = gn.generate_output_message_node(fresh_state)

        assert result.goto == END
        assert fresh_state.conversation.messages[-1].content == "Final answer"
        mock_gen.assert_called_once_with(fresh_state)

    def test_internal_only_tool_results_are_excluded(self, fresh_state: AgentState):
        fresh_state.cognitive.tool_results["get_context_ids"] = {
            "success": True,
            "output": {"context_ids": {}},
        }
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name="get_context_ids", observation_key="get_context_ids")
        ]

        captured = {}

        def fake_generate_answer(state):
            captured["messages"] = list(state.cognitive.messages_to_include)
            return "done"

        with patch.object(gn, "generate_answer", side_effect=fake_generate_answer):
            gn.generate_output_message_node(fresh_state)

        assert captured["messages"] == []

    def test_preexisting_messages_are_not_overwritten(self, fresh_state: AgentState):
        fresh_state.cognitive.tool_results["lookup_glossary"] = {
            "success": True,
            "output": {"matches": []},
        }
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name="lookup_glossary", observation_key="lookup_glossary")
        ]
        fresh_state.cognitive.messages_to_include = ["Please confirm to proceed."]

        captured = {}

        def fake_generate_answer(state):
            captured["messages"] = list(state.cognitive.messages_to_include)
            return "done"

        with patch.object(gn, "generate_answer", side_effect=fake_generate_answer):
            gn.generate_output_message_node(fresh_state)

        assert captured["messages"] == [
            "Please confirm to proceed.",
            "No glossary entries found.",
        ]

    def test_appends_messages_for_every_current_turn_result(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.messages_to_include = ["The tools completed."]
        fresh_state.cognitive.tool_results.update(
            {
                "list_available_problems": {
                    "success": True,
                    "output": {"items": ["problem"]},
                },
                "analyze_scenario_results": {
                    "success": True,
                    "output": {"message": "Analysis is ready."},
                },
            }
        )
        fresh_state.cognitive.scratchpad = [
            ReActStep(
                tool_name="list_available_problems",
                observation_key="list_available_problems",
            ),
            ReActStep(
                tool_name="analyze_scenario_results",
                observation_key="analyze_scenario_results",
            ),
        ]

        captured = {}

        def fake_generate_answer(state):
            captured["messages"] = list(state.cognitive.messages_to_include)
            return "done"

        with patch.object(gn, "generate_answer", side_effect=fake_generate_answer):
            gn.generate_output_message_node(fresh_state)

        assert captured["messages"][0] == "The tools completed."
        assert "Here are the available items" in captured["messages"][1]
        assert captured["messages"][2] == "Analysis is ready."

    def test_scratchpad_reset_when_turn_concludes(self, fresh_state: AgentState):
        fresh_state.cognitive.scratchpad = [ReActStep(tool_name="x")]
        fresh_state.cognitive.tool_result = {"some": "result"}
        fresh_state.waiting_for = None

        with patch.object(gn, "generate_answer", return_value="done"):
            gn.generate_output_message_node(fresh_state)

        assert fresh_state.cognitive.scratchpad == []
        assert fresh_state.cognitive.tool_result is None

    def test_scratchpad_preserved_when_waiting_for_confirmation(
        self, fresh_state: AgentState
    ):
        step = ReActStep(tool_name="x")
        fresh_state.cognitive.scratchpad = [step]
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION

        with patch.object(gn, "generate_answer", return_value="done"):
            gn.generate_output_message_node(fresh_state)

        assert fresh_state.cognitive.scratchpad == [step]

    def test_messages_to_include_cleared_after_use(self, fresh_state: AgentState):
        fresh_state.cognitive.messages_to_include = ["something"]

        with patch.object(gn, "generate_answer", return_value="done"):
            gn.generate_output_message_node(fresh_state)

        assert fresh_state.cognitive.messages_to_include == []

    def test_generate_answer_exception_falls_back_to_system_error(
        self, fresh_state: AgentState
    ):
        with patch.object(gn, "generate_answer", side_effect=RuntimeError("llm down")):
            gn.generate_output_message_node(fresh_state)

        assert fresh_state.conversation.messages[-1].content == "System error"
