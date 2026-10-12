from unittest.mock import patch

import pytest
from langgraph.types import Command

from app.agent.nodes import tool_executor as te
from app.agent.nodes.utils import MAX_STORED_TOOL_RESULTS
from app.agent.state import AgentState, ReActStep
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


# ---------------------------------------------------------------------------
# validate_tool_arguments
# ---------------------------------------------------------------------------


class TestValidateToolArguments:
    def test_passes_when_all_required_present(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True)
            ],
        )
        te.validate_tool_arguments(tool, {"x": "value"})  # should not raise

    def test_raises_on_missing_required_param(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True)
            ],
        )
        with pytest.raises(ValueError, match="Missing required parameter 'x'"):
            te.validate_tool_arguments(tool, {})

    def test_raises_on_null_required_param(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True)
            ],
        )
        with pytest.raises(ValueError, match="cannot be null"):
            te.validate_tool_arguments(tool, {"x": None})

    def test_raises_on_empty_string_required_param(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True)
            ],
        )
        with pytest.raises(ValueError, match="cannot be empty"):
            te.validate_tool_arguments(tool, {"x": "   "})

    def test_optional_param_missing_is_fine(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=False)
            ],
        )
        te.validate_tool_arguments(tool, {})  # should not raise


# ---------------------------------------------------------------------------
# _missing_required_params
# ---------------------------------------------------------------------------


class TestMissingRequiredParams:
    def test_returns_empty_list_when_all_present(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True)
            ],
        )
        assert te._missing_required_params(tool, {"x": "v"}) == []

    def test_returns_missing_names(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True),
                ToolParameter(name="y", description="d", type="string", required=True),
                ToolParameter(name="z", description="d", type="string", required=False),
            ],
        )
        assert te._missing_required_params(tool, {"x": "v"}) == ["y"]

    def test_empty_string_counts_as_missing(self):
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="string", required=True)
            ],
        )
        assert te._missing_required_params(tool, {"x": "  "}) == ["x"]

    def test_non_string_falsy_value_is_not_treated_as_missing(self):
        """Only None or a blank *string* counts as missing — 0 / False are
        legitimate values for non-string required params."""
        tool = ToolDefinition(
            name="t",
            description="d",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter(name="x", description="d", type="integer", required=True)
            ],
        )
        assert te._missing_required_params(tool, {"x": 0}) == []


# ---------------------------------------------------------------------------
# _resolve_referenced_id
# ---------------------------------------------------------------------------


class TestResolveReferencedId:
    def test_unmapped_tool_returns_args_unchanged(self, fresh_state: AgentState):
        args = {"foo": "bar"}
        result = te._resolve_referenced_id(fresh_state, "unmapped_tool", args)
        assert result is args

    def test_explicit_id_is_not_overwritten(self, fresh_state: AgentState):
        fresh_state.cognitive.current_context = {
            "problems": ["p1", "p2"],
            "proposals": [],
            "scenarios": [],
        }
        args = {"problem_id": "explicit"}
        result = te._resolve_referenced_id(fresh_state, "create_new_proposal", args)
        assert result["problem_id"] == "explicit"

    def test_single_candidate_auto_resolves(self, fresh_state: AgentState):
        fresh_state.cognitive.current_context = {
            "problems": ["p1"],
            "proposals": [],
            "scenarios": [],
        }
        args = {}
        result = te._resolve_referenced_id(fresh_state, "create_new_proposal", args)
        assert result["problem_id"] == "p1"

    def test_multiple_candidates_left_unresolved(self, fresh_state: AgentState):
        fresh_state.cognitive.current_context = {
            "problems": ["p1", "p2"],
            "proposals": [],
            "scenarios": [],
        }
        args = {}
        result = te._resolve_referenced_id(fresh_state, "create_new_proposal", args)
        assert "problem_id" not in result

    def test_zero_candidates_left_unresolved(self, fresh_state: AgentState):
        fresh_state.cognitive.current_context = {
            "problems": [],
            "proposals": [],
            "scenarios": [],
        }
        args = {}
        result = te._resolve_referenced_id(fresh_state, "create_new_proposal", args)
        assert "problem_id" not in result

    def test_delete_target_reference_resolution(self, fresh_state: AgentState):
        fresh_state.cognitive.current_context = {
            "problems": ["p1"],
            "proposals": [],
            "scenarios": [],
        }
        result = te._resolve_referenced_id(fresh_state, "delete_problem", {})
        assert result["problem_id"] == "p1"

    def test_does_not_mutate_original_args_dict(self, fresh_state: AgentState):
        fresh_state.cognitive.current_context = {
            "problems": ["p1"],
            "proposals": [],
            "scenarios": [],
        }
        original = {}
        te._resolve_referenced_id(fresh_state, "create_new_proposal", original)
        assert original == {}  # original left untouched; a copy was returned


# ---------------------------------------------------------------------------
# execute_selected_tool / get_tool_executor
# ---------------------------------------------------------------------------


class TestExecuteSelectedTool:
    def test_raises_if_tool_not_registered(self, fresh_state: AgentState):
        with pytest.raises(ValueError, match="not found in registry"):
            te.execute_selected_tool("nonexistent_tool", {}, fresh_state)

    def test_raises_if_tool_disabled(self, fresh_state: AgentState):
        tool = register_tool("lookup_glossary")
        tool.enabled = False
        with pytest.raises(ValueError, match="is disabled"):
            te.execute_selected_tool(
                "lookup_glossary", {"query": "problem"}, fresh_state
            )

    def test_raises_if_required_args_missing(self, fresh_state: AgentState):
        register_tool(
            "lookup_glossary",
            params=[
                ToolParameter(
                    name="query", description="d", type="string", required=True
                )
            ],
        )
        with pytest.raises(ValueError, match="Missing required parameter"):
            te.execute_selected_tool("lookup_glossary", {}, fresh_state)

    def test_successful_execution_returns_wrapped_result(self, fresh_state: AgentState):
        register_tool(
            "lookup_glossary",
            params=[
                ToolParameter(
                    name="query", description="d", type="string", required=True
                )
            ],
        )
        result = te.execute_selected_tool(
            "lookup_glossary", {"query": "problem"}, fresh_state
        )
        assert result["success"] is True
        assert result["error"] is None
        assert "matches" in result["output"]

    def test_executor_exception_is_caught_and_wrapped(self, fresh_state: AgentState):
        register_tool("get_context_details")
        # get_context_details makes a real backend_tools call; force failure
        # by leaving current_context invalid to trigger an internal error.
        with patch.object(te, "get_tool_executor") as mock_get_executor:

            def boom(state, **kwargs):
                raise RuntimeError("kaboom")

            mock_get_executor.return_value = boom
            result = te.execute_selected_tool("get_context_details", {}, fresh_state)
        assert result["success"] is False
        assert result["output"] is None
        assert "kaboom" in result["error"]

    def test_no_executor_implemented_raises_not_implemented(
        self, fresh_state: AgentState
    ):
        register_tool("totally_custom_tool")
        with patch.object(te, "get_tool_executor", return_value=None):
            with pytest.raises(NotImplementedError):
                te.execute_selected_tool("totally_custom_tool", {}, fresh_state)


class TestGetToolExecutor:
    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_system_capabilities",
            "list_available_problems",
            "list_available_proposals",
            "list_available_scenarios",
            "get_context_ids",
            "get_context_details",
            "get_base_scenario",
            "analyze_scenario_results",
            "create_new_problem",
            "create_new_proposal",
            "create_new_scenario",
            "edit_problem",
            "edit_proposal",
            "edit_scenario",
            "delete_problem",
            "delete_proposal",
            "delete_scenario",
            "lookup_glossary",
        ],
    )
    def test_known_tools_have_an_executor(self, tool_name):
        assert te.get_tool_executor(tool_name) is not None

    def test_unknown_tool_returns_none(self):
        assert te.get_tool_executor("not_a_real_tool") is None


# ---------------------------------------------------------------------------
# _trim_tool_results
# ---------------------------------------------------------------------------


class TestTrimToolResults:
    def test_no_trim_needed_under_cap(self, fresh_state: AgentState):
        fresh_state.cognitive.tool_results = {f"k{i}": i for i in range(5)}
        te._trim_tool_results(fresh_state)
        assert len(fresh_state.cognitive.tool_results) == 5

    def test_evicts_oldest_first_over_cap(self, fresh_state: AgentState):
        fresh_state.cognitive.tool_results = {
            f"k{i}": i for i in range(MAX_STORED_TOOL_RESULTS + 5)
        }
        te._trim_tool_results(fresh_state)
        assert len(fresh_state.cognitive.tool_results) == MAX_STORED_TOOL_RESULTS
        # oldest keys (k0..k4) evicted
        for i in range(5):
            assert f"k{i}" not in fresh_state.cognitive.tool_results
        assert f"k{MAX_STORED_TOOL_RESULTS + 4}" in fresh_state.cognitive.tool_results

    def test_never_evicts_current_turn_keys(self, fresh_state: AgentState):
        # Fill over the cap entirely with "current turn" keys.
        n = MAX_STORED_TOOL_RESULTS + 3
        fresh_state.cognitive.tool_results = {f"cur{i}": i for i in range(n)}
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name=f"cur{i}", observation_key=f"cur{i}") for i in range(n)
        ]
        te._trim_tool_results(fresh_state)
        # Nothing could be evicted since all keys are protected.
        assert len(fresh_state.cognitive.tool_results) == n

    def test_evicts_non_protected_before_protected(self, fresh_state: AgentState):
        n_protected = 5
        n_old = MAX_STORED_TOOL_RESULTS
        results = {f"old{i}": i for i in range(n_old)}
        results.update({f"cur{i}": i for i in range(n_protected)})
        fresh_state.cognitive.tool_results = results
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name=f"cur{i}", observation_key=f"cur{i}")
            for i in range(n_protected)
        ]
        te._trim_tool_results(fresh_state)
        assert len(fresh_state.cognitive.tool_results) == MAX_STORED_TOOL_RESULTS
        for i in range(n_protected):
            assert f"cur{i}" in fresh_state.cognitive.tool_results


# ---------------------------------------------------------------------------
# execute_lookup_glossary
# ---------------------------------------------------------------------------


class TestExecuteLookupGlossary:
    def test_empty_query_returns_failure(self, fresh_state: AgentState):
        result = te.execute_lookup_glossary(fresh_state, query="   ")
        assert result["success"] is False
        assert result["matches"] == []

    def test_matches_by_term_name(self, fresh_state: AgentState):
        result = te.execute_lookup_glossary(fresh_state, query="proposal")
        assert result["success"] is True
        terms = {m["term"] for m in result["matches"]}
        assert "proposal" in terms

    def test_matches_by_alias(self, fresh_state: AgentState):
        result = te.execute_lookup_glossary(fresh_state, query="strategy")
        terms = {m["term"] for m in result["matches"]}
        assert "proposal" in terms  # "strategy" is an alias of "proposal"

    def test_no_match_returns_helpful_message(self, fresh_state: AgentState):
        result = te.execute_lookup_glossary(fresh_state, query="xyzzy_nonexistent")
        assert result["success"] is True
        assert result["matches"] == []
        assert "No glossary entries found" in result["message"]

    def test_multi_token_query_matches_any_token(self, fresh_state: AgentState):
        result = te.execute_lookup_glossary(fresh_state, query="unrelatedword scenario")
        terms = {m["term"] for m in result["matches"]}
        assert "scenario" in terms


# ---------------------------------------------------------------------------
# tool_executor_node — high-level flow
# ---------------------------------------------------------------------------


class TestToolExecutorNode:
    def test_no_pending_action_routes_to_output(self, fresh_state: AgentState):
        fresh_state.cognitive.selected_tool = None
        result = te.tool_executor_node(fresh_state)
        assert result.goto == "generate_output_message"

    def test_missing_required_params_asks_user_and_skips_confirmation(
        self, fresh_state: AgentState
    ):
        register_tool(
            "create_new_problem",
            params=[
                ToolParameter(
                    name="name", description="d", type="string", required=True
                ),
                ToolParameter(
                    name="description", description="d", type="string", required=True
                ),
            ],
        )
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {"name": "Overtourism"}

        result = te.tool_executor_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.tool_confirmation_needed is False
        assert "description" in fresh_state.cognitive.messages_to_include[0]

    def test_confirmation_required_tool_pauses_first_time(
        self, fresh_state: AgentState
    ):
        register_tool(
            "create_new_problem",
            params=[
                ToolParameter(
                    name="name", description="d", type="string", required=True
                )
            ],
        )
        fresh_state.cognitive.selected_tool = "create_new_problem"
        fresh_state.cognitive.tool_arguments = {"name": "Overtourism"}
        fresh_state.cognitive.tool_confirmed = False

        result = te.tool_executor_node(fresh_state)

        assert result.goto == "WAIT_USER_INPUT"
        assert fresh_state.cognitive.tool_confirmation_needed is True

    def test_confirmed_tool_executes_and_routes_to_reasoner(
        self, fresh_state: AgentState
    ):
        register_tool(
            "lookup_glossary",
            params=[
                ToolParameter(
                    name="query", description="d", type="string", required=True
                )
            ],
        )
        fresh_state.cognitive.selected_tool = "lookup_glossary"
        fresh_state.cognitive.tool_arguments = {"query": "problem"}
        fresh_state.cognitive.tool_confirmed = False  # not a confirmation-required tool

        result = te.tool_executor_node(fresh_state)

        assert result.goto == "react_reasoner"
        assert fresh_state.cognitive.selected_tool is None
        assert fresh_state.cognitive.tool_arguments == {}
        assert len(fresh_state.cognitive.scratchpad) == 1
        assert fresh_state.cognitive.scratchpad[0].tool_name == "lookup_glossary"
        assert "lookup_glossary" in fresh_state.cognitive.tool_results

    def test_failed_tool_execution_routes_to_error(self, fresh_state: AgentState):
        register_tool("get_context_details")
        with patch.object(te, "get_tool_executor") as mock_get_executor:

            def boom(state, **kwargs):
                raise RuntimeError("backend down")

            mock_get_executor.return_value = boom
            fresh_state.cognitive.selected_tool = "get_context_details"
            fresh_state.cognitive.tool_arguments = {}
            result = te.tool_executor_node(fresh_state)

        assert result.goto == "error"
        assert "backend down" in fresh_state.cognitive.error_details

    def test_result_key_collision_gets_suffixed(self, fresh_state: AgentState):
        register_tool(
            "lookup_glossary",
            params=[
                ToolParameter(
                    name="query", description="d", type="string", required=True
                )
            ],
        )
        fresh_state.cognitive.tool_results["lookup_glossary"] = {"already": "there"}
        fresh_state.cognitive.selected_tool = "lookup_glossary"
        fresh_state.cognitive.tool_arguments = {"query": "problem"}

        te.tool_executor_node(fresh_state)

        assert "lookup_glossary__1" in fresh_state.cognitive.tool_results
        assert (
            fresh_state.cognitive.scratchpad[0].observation_key == "lookup_glossary__1"
        )

    def test_confirmed_flag_is_consumed_after_use(self, fresh_state: AgentState):
        register_tool(
            "lookup_glossary",
            params=[
                ToolParameter(
                    name="query", description="d", type="string", required=True
                )
            ],
        )
        fresh_state.cognitive.selected_tool = "lookup_glossary"
        fresh_state.cognitive.tool_arguments = {"query": "problem"}
        fresh_state.cognitive.tool_confirmed = True

        te.tool_executor_node(fresh_state)

        assert fresh_state.cognitive.tool_confirmed is False

    def test_auto_resolved_id_is_used_in_execution(self, fresh_state: AgentState):
        register_tool(
            "delete_problem",
            params=[
                ToolParameter(
                    name="problem_id", description="d", type="string", required=True
                )
            ],
        )
        fresh_state.cognitive.current_context = {
            "problems": ["p123"],
            "proposals": [],
            "scenarios": [],
        }
        fresh_state.cognitive.selected_tool = "delete_problem"
        fresh_state.cognitive.tool_arguments = {}
        fresh_state.cognitive.tool_confirmed = True  # skip the confirmation gate

        with patch.object(te, "get_tool_executor") as mock_get_executor:
            captured = {}

            def fake_executor(state, **kwargs):
                captured.update(kwargs)
                return {"success": True, "name": "resolved-problem"}

            mock_get_executor.return_value = fake_executor
            te.tool_executor_node(fresh_state)

        assert captured["problem_id"] == "p123"
