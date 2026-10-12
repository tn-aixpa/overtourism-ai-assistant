"""
Tier 1 — deterministic routing tests.

These test *your code*: given a fixed (mocked) LLM decision, does
react_reasoner_node route to the right place, enforce the enabled-tools
allowlist, and handle malformed/hallucinated responses safely? No real
Anthropic calls are made — see test_reasoner_eval.py for that.
"""

import json
from unittest.mock import patch

import pytest
from langgraph.types import Command

from app.agent.nodes import reasoner as reasoner_module
from app.agent.state import AgentState, ReActStep
from app.prompts.react_guidelines import GUIDELINE_BLOCKS
from app.tools.definitions.analysis_widgets import create_analysis_widget_tool
from app.tools.definitions.indexes import create_show_territorial_index_map_tool
from app.tools.tool_registry import get_tool_registry
from app.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter


def register_tool(name, params=None):
    tool = ToolDefinition(
        name=name,
        description="d",
        category=ToolCategory.UTILITY,
        parameters=params or [],
    )
    get_tool_registry().register_tool(tool)
    return tool


def react_step_response(**overrides):
    payload = {"thought": "reasoning...", "action": "finish", "message": "done"}
    payload.update(overrides)
    return json.dumps(payload)


def test_scenario_guidelines_require_preview_plot_and_respect_viewer_permissions():
    scenario_guidelines = "\n".join(
        body for _, body in GUIDELINE_BLOCKS["scenario_analysis"]
    )

    assert "After create_new_temp_scenario returns created=true" in scenario_guidelines
    assert "widget_type='load_plot'" in scenario_guidelines
    assert "do not offer saving as an option" in scenario_guidelines
    assert (
        "Do NOT call a write tool, ask for a name/description/proposal"
        in scenario_guidelines
    )


def test_existing_scenario_questions_always_include_evaluation_and_plot():
    scenario_guidelines = "\n".join(
        body for _, body in GUIDELINE_BLOCKS["scenario_analysis"]
    )

    assert "ALWAYS assume a request about an existing scenario" in scenario_guidelines
    assert (
        "call analyze_scenario_results to report its evaluation" in scenario_guidelines
    )
    assert "For a SINGLE existing scenario" in scenario_guidelines
    assert "widget_type='load_plot'" in scenario_guidelines


# ---------------------------------------------------------------------------
# initialize_tools
# ---------------------------------------------------------------------------


class TestInitializeTools:
    def test_registers_default_tools_when_registry_empty(self, fresh_state: AgentState):
        assert get_tool_registry().list_tool_names() == []
        reasoner_module.initialize_tools(fresh_state)
        assert len(get_tool_registry().list_tool_names()) > 0

    def test_does_not_reregister_if_already_populated(self, fresh_state: AgentState):
        register_tool("custom_only_tool")
        reasoner_module.initialize_tools(fresh_state)
        # Registration is guarded by "if registry is empty" — since it
        # already had one tool, the real default toolset (e.g.
        # "lookup_glossary") must NOT have been added alongside it.
        names = get_tool_registry().list_tool_names()
        assert names == ["custom_only_tool"]

    def test_non_integrated_mode_enables_all_known_tools(self, fresh_state: AgentState):
        register_tool("a")
        register_tool("b")
        fresh_state.integrated_mode = False
        result = reasoner_module.initialize_tools(fresh_state)
        assert set(fresh_state.cognitive.enabled_tools) == {"a", "b"}
        assert result.goto == "top_level_router"

    def test_integrated_mode_preserves_preset_enabled_tools(
        self, fresh_state: AgentState
    ):
        register_tool("a")
        register_tool("b")
        fresh_state.integrated_mode = True
        fresh_state.cognitive.enabled_tools = ["a"]  # route already restricted this
        reasoner_module.initialize_tools(fresh_state)
        assert fresh_state.cognitive.enabled_tools == ["a"]

    def test_widget_tools_are_visible_in_standalone_and_hidden_in_integrated_mode(
        self, fresh_state: AgentState
    ):
        get_tool_registry().register_tool(create_analysis_widget_tool())

        fresh_state.integrated_mode = False
        fresh_state.session_mode = "standalone"
        reasoner_module.initialize_tools(fresh_state)
        assert "show_analysis_widget" in fresh_state.cognitive.enabled_tools

        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = ["a"]
        reasoner_module.initialize_tools(fresh_state)
        assert "show_analysis_widget" not in fresh_state.cognitive.enabled_tools

    def test_territorial_index_map_is_available_in_standalone_mode(
        self, fresh_state: AgentState
    ):
        get_tool_registry().register_tool(create_show_territorial_index_map_tool())

        fresh_state.integrated_mode = False
        reasoner_module.initialize_tools(fresh_state)

        assert "show_territorial_index_map" in fresh_state.cognitive.enabled_tools

        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = ["show_territorial_index_map"]
        reasoner_module.initialize_tools(fresh_state)

        assert "show_territorial_index_map" not in fresh_state.cognitive.enabled_tools

    def test_resets_scratchpad_and_pending_action_on_fresh_turn(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.scratchpad = [ReActStep(tool_name="x")]
        fresh_state.cognitive.selected_tool = "x"
        fresh_state.cognitive.tool_arguments = {"a": 1}
        fresh_state.cognitive.pending_thought = "old thought"
        fresh_state.cognitive.tool_confirmation_needed = True
        fresh_state.cognitive.tool_confirmed = True

        reasoner_module.initialize_tools(fresh_state)

        assert fresh_state.cognitive.scratchpad == []
        assert fresh_state.cognitive.selected_tool is None
        assert fresh_state.cognitive.tool_arguments == {}
        assert fresh_state.cognitive.pending_thought == ""
        assert fresh_state.cognitive.tool_confirmation_needed is False
        assert fresh_state.cognitive.tool_confirmed is False

    def test_does_not_touch_long_term_tool_results(self, fresh_state: AgentState):
        fresh_state.cognitive.tool_results = {"lookup_glossary": {"success": True}}
        reasoner_module.initialize_tools(fresh_state)
        assert fresh_state.cognitive.tool_results == {
            "lookup_glossary": {"success": True}
        }

    def test_pending_confirmation_with_user_input_routes_to_wait_node(
        self, fresh_state: AgentState
    ):
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = "yes"
        result = reasoner_module.initialize_tools(fresh_state)
        assert result.goto == "WAIT_USER_INPUT"

    def test_waiting_for_without_user_input_does_not_short_circuit(
        self, fresh_state: AgentState
    ):
        """waiting_for alone (no reply yet) shouldn't resume — only
        waiting_for + user_input together mean 'the user just replied'."""
        register_tool("a")
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = None
        result = reasoner_module.initialize_tools(fresh_state)
        assert result.goto == "top_level_router"


# ---------------------------------------------------------------------------
# react_reasoner_node — tool selection
# ---------------------------------------------------------------------------


class TestReactReasonerToolSelection:
    def test_reports_role_and_mode_restrictions_separately(
        self, fresh_state: AgentState
    ):
        register_tool("read_tool")
        get_tool_registry().register_tool(
            ToolDefinition(
                name="save_tool",
                description="d",
                category=ToolCategory.UTILITY,
                allowed_roles=("admin", "editor"),
            )
        )
        get_tool_registry().register_tool(
            ToolDefinition(
                name="internal_tool",
                description="d",
                category=ToolCategory.UTILITY,
                allowed_modes=("internal",),
            )
        )
        fresh_state.user_role = "viewer"
        fresh_state.session_mode = "standalone"
        fresh_state.cognitive.enabled_tools = ["read_tool"]

        with patch.object(
            reasoner_module, "react_step", return_value=react_step_response()
        ) as mock_react_step:
            reasoner_module.react_reasoner_node(fresh_state)

        assert mock_react_step.call_args.args[2] == ["internal_tool"]
        assert mock_react_step.call_args.args[3] == ["save_tool"]

    def test_selects_enabled_tool_and_stages_it_for_execution(
        self, fresh_state: AgentState
    ):
        register_tool(
            "lookup_glossary",
            [ToolParameter(name="query", description="d", type="string")],
        )
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(
            action="tool", tool_name="lookup_glossary", arguments={"query": "problem"}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == "lookup_glossary"
        assert fresh_state.cognitive.tool_arguments == {"query": "problem"}
        assert fresh_state.cognitive.pending_thought == "reasoning..."

    def test_rejects_tool_not_in_enabled_allowlist(self, fresh_state: AgentState):
        """Registered globally but not enabled in this context (e.g. scoped
        by integrated mode) — must not be dispatched even if the model asks."""
        register_tool("delete_problem")
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(
            action="tool", tool_name="delete_problem", arguments={}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.selected_tool is None
        assert fresh_state.cognitive.messages_to_include == [
            "The current request cannot be handled in the current context. "
            "Please change context or use the standalone chat."
        ]

    def test_hallucinated_tool_name_finishes_safely(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(
            action="tool", tool_name="tool_that_does_not_exist", arguments={}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.selected_tool is None

    def test_missing_tool_name_with_tool_action_finishes_safely(
        self, fresh_state: AgentState
    ):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(action="tool", tool_name=None, arguments={})

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"

    def test_missing_arguments_defaults_to_empty_dict(self, fresh_state: AgentState):
        register_tool("get_system_capabilities")
        fresh_state.cognitive.enabled_tools = ["get_system_capabilities"]
        raw = json.dumps(
            {"thought": "t", "action": "tool", "tool_name": "get_system_capabilities"}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.tool_arguments == {}

    def test_finish_action_sets_message_and_ends_turn(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(action="finish", message="Here's your answer.")

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.messages_to_include == ["Here's your answer."]

    def test_finish_action_without_message_uses_fallback(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = json.dumps({"thought": "t", "action": "finish"})

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert fresh_state.cognitive.messages_to_include == [
            "Could you clarify your request?"
        ]

    def test_unrecognized_action_value_finishes_safely(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        raw = react_step_response(action="do_a_backflip", message="n/a")

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"

    def test_no_tools_available_at_all_finishes_immediately(
        self, fresh_state: AgentState
    ):
        # Registry has zero tools registered at all (not just zero enabled).
        result = reasoner_module.react_reasoner_node(fresh_state)
        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.messages_to_include == [
            "No tools are available in the current context."
        ]

    def test_max_react_steps_forces_finish_without_calling_llm(
        self, fresh_state: AgentState
    ):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name=f"step_{i}")
            for i in range(fresh_state.cognitive.max_react_steps)
        ]

        with patch.object(reasoner_module, "react_step") as mock_react_step:
            result = reasoner_module.react_reasoner_node(fresh_state)

        mock_react_step.assert_not_called()
        assert result.goto == "generate_output_message"
        # The safety-valve path deliberately leaves messages_to_include
        # empty so generate_output_message falls back to synthesizing from
        # every observation collected this turn.
        assert fresh_state.cognitive.messages_to_include == []

    def test_malformed_llm_json_routes_to_error(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        with patch.object(
            reasoner_module, "react_step", return_value="not valid json {{{"
        ):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "error"
        assert fresh_state.cognitive.error_details

    def test_markdown_fenced_json_is_unwrapped(self, fresh_state: AgentState):
        """Models sometimes wrap JSON in ```json ... ``` fences despite being
        told not to — react_reasoner_node must strip that before parsing."""
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = (
            "```json\n"
            + react_step_response(
                action="tool",
                tool_name="lookup_glossary",
                arguments={"query": "scenario"},
            )
            + "\n```"
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == "lookup_glossary"

    def test_trace_step_recorded_for_each_decision(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(action="finish", message="done")

        with patch.object(reasoner_module, "react_step", return_value=raw):
            reasoner_module.react_reasoner_node(fresh_state)

        trace_steps = [
            s
            for s in fresh_state.cognitive.trace.steps
            if s.step_type == "react_thought"
        ]
        assert len(trace_steps) == 1
        assert trace_steps[0].data["action"] == "finish"


# ---------------------------------------------------------------------------
# Parametrized "correct tool for this LLM decision" table
# ---------------------------------------------------------------------------


class TestToolSelectionTable:
    """A compact table of (mocked LLM decision -> expected routing outcome),
    useful as a single place to extend when a new tool is added."""

    @pytest.mark.parametrize(
        "tool_name,arguments",
        [
            ("get_system_capabilities", {}),
            ("list_available_problems", {}),
            (
                "get_context_ids",
                {
                    "user_intent": "overtourism",
                    "source_tools": ["list_available_problems"],
                },
            ),
            ("analyze_scenario_results", {"query": "what is the KPI?"}),
            ("create_new_problem", {"name": "N", "description": "D"}),
            ("lookup_glossary", {"query": "scenario"}),
        ],
    )
    def test_each_known_tool_can_be_selected_when_enabled(
        self, fresh_state, tool_name, arguments
    ):
        register_tool(tool_name)
        fresh_state.cognitive.enabled_tools = [tool_name]
        raw = react_step_response(
            action="tool", tool_name=tool_name, arguments=arguments
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == tool_name
        assert fresh_state.cognitive.tool_arguments == arguments
