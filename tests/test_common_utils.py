import json

import pytest

from app.utils.common import (
    DEFAULT_MAX_FIELD_CHARS,
    DEFAULT_MAX_ITEMS_FOR_MATCHING,
    GraphError,
    RequestHandlingException,
    _condense_object,
    _truncate_json,
    build_prior_results_block,
    condense_for_matching,
    enforce_prompt_budget,
    get_token,
    set_token,
    truncate_for_prompt,
)

# ---------------------------------------------------------------------------
# _condense_object / condense_for_matching
# ---------------------------------------------------------------------------


class TestCondenseObject:
    def test_drops_heavy_fields(self):
        obj = {
            "id": "1",
            "name": "n",
            "extras": {"big": "data"},
            "evaluation_data": [1, 2],
        }
        condensed = _condense_object(obj)
        assert "extras" not in condensed
        assert "evaluation_data" not in condensed
        assert condensed == {"id": "1", "name": "n"}

    def test_truncates_long_string_fields(self):
        obj = {"description": "x" * 500}
        condensed = _condense_object(obj, max_field_chars=100)
        assert condensed["description"].startswith("x" * 100)
        assert "400 chars omitted" in condensed["description"]

    def test_leaves_short_strings_untouched(self):
        obj = {"name": "short"}
        assert _condense_object(obj) == {"name": "short"}

    def test_non_dict_passthrough(self):
        assert _condense_object("not a dict") == "not a dict"
        assert _condense_object(42) == 42


class TestCondenseForMatching:
    def test_list_under_max_items_returned_as_plain_list(self):
        data = [{"id": str(i), "name": f"item{i}"} for i in range(3)]
        result = condense_for_matching(data, max_items=5)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_list_over_max_items_summarizes_overflow(self):
        data = [{"id": str(i), "name": f"item{i}"} for i in range(5)]
        result = condense_for_matching(data, max_items=3)
        assert isinstance(result, dict)
        assert len(result["items"]) == 3
        assert "2 additional item(s)" in result["note"]
        assert "'3'" in result["note"] or "3" in result["note"]

    def test_overflow_uses_name_when_no_id(self):
        data = [{"id": str(i)} for i in range(3)] + [{"name": "only-name"}]
        result = condense_for_matching(data, max_items=3)
        assert result["note"].count("1 additional") == 1
        assert "only-name" in result["note"]

    def test_overflow_item_not_dict_uses_placeholder(self):
        data = ["a", "b", "c", "d"]
        result = condense_for_matching(data, max_items=3)
        assert "?" in result["note"]

    def test_dict_input_recurses_into_values(self):
        data = {"problems": [{"id": "1", "name": "p"}], "count": 1}
        result = condense_for_matching(data)
        assert result["problems"] == [{"id": "1", "name": "p"}]
        assert result["count"] == 1

    def test_scalar_passthrough(self):
        assert condense_for_matching("hello") == "hello"
        assert condense_for_matching(5) == 5
        assert condense_for_matching(None) is None

    def test_default_constants_are_reasonable(self):
        assert DEFAULT_MAX_ITEMS_FOR_MATCHING == 40
        assert DEFAULT_MAX_FIELD_CHARS == 300


# ---------------------------------------------------------------------------
# _truncate_json / truncate_for_prompt
# ---------------------------------------------------------------------------


class TestTruncateJson:
    def test_short_object_not_truncated(self):
        result = _truncate_json({"a": 1}, max_chars=1000)
        assert json.loads(result) == {"a": 1}

    def test_long_object_is_truncated_with_marker(self):
        obj = {"data": "x" * 1000}
        result = _truncate_json(obj, max_chars=50)
        assert len(result) > 50  # marker text pushes it over max_chars
        assert "truncated" in result
        assert result.startswith('{\n  "data"')

    def test_unserializable_object_falls_back_to_str(self):
        class Weird:
            def __repr__(self):
                return "WeirdRepr"

        # default=str is passed to json.dumps, so this actually succeeds
        # via str() rather than raising — verify it doesn't crash either way.
        result = _truncate_json(Weird(), max_chars=1000)
        assert "WeirdRepr" in result

    def test_truncate_for_prompt_is_public_wrapper(self):
        obj = {"a": 1}
        assert truncate_for_prompt(obj) == _truncate_json(obj, 1200)


# ---------------------------------------------------------------------------
# enforce_prompt_budget
# ---------------------------------------------------------------------------


class TestEnforcePromptBudget:
    def test_short_prompt_untouched(self):
        prompt = "short prompt"
        assert enforce_prompt_budget(prompt, max_chars=1000) == prompt

    def test_prompt_exactly_at_budget_untouched(self):
        prompt = "x" * 100
        assert enforce_prompt_budget(prompt, max_chars=100) == prompt

    def test_long_prompt_truncates_middle_keeps_head_and_tail(self):
        prompt = "HEAD" + "x" * 1000 + "TAIL"
        result = enforce_prompt_budget(prompt, max_chars=100)
        assert result.startswith("HEAD")
        assert result.endswith("TAIL")
        assert "truncated" in result
        assert len(result) < len(prompt)


# ---------------------------------------------------------------------------
# build_prior_results_block
# ---------------------------------------------------------------------------


class TestBuildPriorResultsBlock:
    def test_empty_results_returns_none_string(self):
        assert build_prior_results_block({}) == "None"

    def test_shows_all_entries_under_max(self):
        results = {"tool_a": {"x": 1}, "tool_b": {"y": 2}}
        block = build_prior_results_block(results, max_entries=6)
        assert "### tool_a" in block
        assert "### tool_b" in block
        assert "omitted" not in block

    def test_omits_older_entries_beyond_max(self):
        results = {f"tool_{i}": {"v": i} for i in range(8)}
        block = build_prior_results_block(results, max_entries=3)
        # Only the last 3 keys are shown in full.
        for i in range(5, 8):
            assert f"### tool_{i}" in block
        for i in range(0, 5):
            assert f"### tool_{i}" not in block
        assert "5 older SUCCESSFUL result(s) omitted" in block
        assert "tool_0" in block  # omitted keys are still named

    def test_each_entry_truncated_per_entry_limit(self):
        results = {"tool_a": {"data": "x" * 5000}}
        block = build_prior_results_block(results, max_chars_per_entry=100)
        assert "truncated" in block


# ---------------------------------------------------------------------------
# token contextvar
# ---------------------------------------------------------------------------


class TestTokenContextVar:
    @pytest.fixture(autouse=True)
    def _reset_token(self):
        """Reset the module-level ContextVar before and after each test so
        tests are independent of execution order."""
        from app.utils import common as common_module

        common_module._current_token.set(None)
        yield
        common_module._current_token.set(None)

    def test_get_token_without_set_raises(self):
        with pytest.raises(RuntimeError, match="No auth token set"):
            get_token()

    def test_set_then_get_token_roundtrip(self):
        set_token("my-token")
        assert get_token() == "my-token"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_graph_error_stores_details(self):
        err = GraphError("something broke")
        assert err.details == "something broke"
        assert str(err) == "something broke"

    def test_graph_error_details_optional(self):
        err = GraphError()
        assert err.details is None

    def test_request_handling_exception_is_a_graph_error(self):
        err = RequestHandlingException("bad request")
        assert isinstance(err, GraphError)
        assert err.details == "bad request"
