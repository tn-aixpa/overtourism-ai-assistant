import pytest
from pydantic import ValidationError

from app.schemas import AgentResponse, RunSelectedToolsRequest, ToolStep


class TestRunSelectedToolsRequest:
    @pytest.mark.parametrize("key", ["summary", "pdf-report"])
    def test_accepts_the_supported_keys(self, key):
        assert RunSelectedToolsRequest(key=key).key == key

    @pytest.mark.parametrize("key", ["", "report", "SUMMARY", "pdf_report"])
    def test_rejects_other_keys(self, key):
        with pytest.raises(ValidationError):
            RunSelectedToolsRequest(key=key)

    def test_key_is_required(self):
        with pytest.raises(ValidationError):
            RunSelectedToolsRequest()

    def test_defaults(self):
        req = RunSelectedToolsRequest(key="summary")

        assert req.steps == []
        assert req.current_context is None
        assert req.stop_on_error is True

    def test_current_context_may_hold_lists_and_nested_temp_dicts(self):
        ctx = {"scenarios": ["a"], "temp": {"creation_session": "c", "evaluation_id": "e"}}

        assert RunSelectedToolsRequest(key="summary", current_context=ctx).current_context == ctx

    def test_steps_are_parsed_into_toolsteps(self):
        req = RunSelectedToolsRequest(key="summary", steps=[{"tool_name": "x"}])

        assert req.steps == [ToolStep(tool_name="x", arguments={})]

    def test_default_lists_are_not_shared_between_instances(self):
        a, b = RunSelectedToolsRequest(key="summary"), RunSelectedToolsRequest(key="summary")
        a.steps.append(ToolStep(tool_name="x"))

        assert b.steps == []


class TestAgentResponse:
    def test_requires_session_and_agent_type(self):
        with pytest.raises(ValidationError):
            AgentResponse(session_id="s")

    def test_response_and_actions_are_optional(self):
        r = AgentResponse(session_id="s", agent_type="executor")

        assert r.response is None and r.assistant_action_data is None

    def test_extra_fields_are_allowed(self):
        r = AgentResponse(session_id="s", agent_type="executor", anything="goes")

        assert r.model_dump()["anything"] == "goes"
