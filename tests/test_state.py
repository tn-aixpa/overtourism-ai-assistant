import json
from datetime import datetime

import pytest

from app.agent.state import (
    AgentState,
    AssistantMessage,
    CognitiveState,
    ConversationBuffer,
    DEFAULT_REASONING_CONTEXT_SIZE,
    ReActStep,
    TraceBuffer,
    TraceStep,
    UserMessage,
)

# ---------------------------------------------------------------------------
# ConversationBuffer
# ---------------------------------------------------------------------------


class TestConversationBuffer:
    def test_add_message_appends(self):
        buf = ConversationBuffer()
        buf.add_message(UserMessage(content="hi"))
        assert len(buf.messages) == 1
        assert buf.messages[0].content == "hi"

    def test_get_last_n_default_uses_max_window_size(self):
        buf = ConversationBuffer(max_window_size=2)
        for i in range(5):
            buf.add_message(UserMessage(content=str(i)))
        last = buf.get_last_n()
        assert [m.content for m in last] == ["3", "4"]

    def test_get_last_n_explicit_n(self):
        buf = ConversationBuffer()
        for i in range(5):
            buf.add_message(UserMessage(content=str(i)))
        last = buf.get_last_n(3)
        assert [m.content for m in last] == ["2", "3", "4"]

    def test_get_context_window_formats_for_llm(self):
        buf = ConversationBuffer()
        buf.add_message(UserMessage(content="hello"))
        buf.add_message(AssistantMessage(content="hi there"))
        window = buf.get_context_window()
        assert window == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def test_get_last_n_on_empty_buffer(self):
        buf = ConversationBuffer()
        assert buf.get_last_n() == []
        assert buf.get_context_window() == []


# ---------------------------------------------------------------------------
# TraceBuffer
# ---------------------------------------------------------------------------


class TestTraceBuffer:
    def test_add_step_appends(self):
        trace = TraceBuffer()
        trace.add_step(TraceStep(step_type="thought", node="react_reasoner"))
        assert len(trace.steps) == 1

    def test_trims_to_max_trace_size(self):
        trace = TraceBuffer(max_trace_size=3)
        for i in range(10):
            trace.add_step(TraceStep(step_type="s", node=str(i)))
        assert len(trace.steps) == 3
        # Oldest steps are dropped, most recent are kept, in order.
        assert [s.node for s in trace.steps] == ["7", "8", "9"]

    def test_get_last_n(self):
        trace = TraceBuffer()
        for i in range(5):
            trace.add_step(TraceStep(step_type="s", node=str(i)))
        assert [s.node for s in trace.get_last_n(2)] == ["3", "4"]


# ---------------------------------------------------------------------------
# CognitiveState
# ---------------------------------------------------------------------------


class TestCognitiveState:
    def test_default_current_context_has_three_empty_lists(self):
        cog = CognitiveState()
        assert cog.current_context == {"problems": [], "proposals": [], "scenarios": []}

    def test_two_instances_do_not_share_mutable_defaults(self):
        """Regression guard: default_factory must produce independent dicts/
        lists per instance, not a shared mutable default."""
        cog1 = CognitiveState()
        cog2 = CognitiveState()
        cog1.current_context["problems"].append("p1")
        cog1.tool_results["k"] = "v"
        assert cog2.current_context["problems"] == []
        assert cog2.tool_results == {}

    def test_current_turn_result_keys_only_includes_steps_with_a_key(self):
        cog = CognitiveState()
        cog.scratchpad = [
            ReActStep(tool_name="a", observation_key="a_key"),
            ReActStep(tool_name="b", observation_key=None),
            ReActStep(tool_name="c", observation_key="c_key"),
        ]
        assert cog.current_turn_result_keys() == ["a_key", "c_key"]

    def test_current_turn_result_keys_empty_scratchpad(self):
        cog = CognitiveState()
        assert cog.current_turn_result_keys() == []

    def test_add_trace_appends_to_trace_buffer(self):
        cog = CognitiveState()
        cog._add_trace("thought", "react_reasoner", {"foo": "bar"})
        assert len(cog.trace.steps) == 1
        assert cog.trace.steps[0].data == {"foo": "bar"}


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------


class TestAgentStateMessages:
    def test_add_user_message(self, fresh_state: AgentState):
        fresh_state.add_user_message("hello")
        assert len(fresh_state.conversation.messages) == 1
        assert fresh_state.conversation.messages[0].role == "user"
        assert fresh_state.conversation.messages[0].content == "hello"

    def test_get_last_user_message_skips_assistant_messages(
        self, fresh_state: AgentState
    ):
        fresh_state.add_user_message("first")
        fresh_state.add_assistant_message("a reply")
        fresh_state.add_user_message("second")
        assert fresh_state.get_last_user_message().content == "second"

    def test_get_last_user_message_returns_none_when_absent(
        self, fresh_state: AgentState
    ):
        assert fresh_state.get_last_user_message() is None
        fresh_state.add_assistant_message("only assistant")
        assert fresh_state.get_last_user_message() is None

    def test_get_last_message_returns_most_recent_of_any_role(
        self, fresh_state: AgentState
    ):
        fresh_state.add_user_message("first")
        fresh_state.add_assistant_message("second")
        assert fresh_state.get_last_message().content == "second"

    def test_get_last_message_empty(self, fresh_state: AgentState):
        assert fresh_state.get_last_message() is None

    def test_get_reasoning_context_uses_default_size(self, fresh_state: AgentState):
        for i in range(10):
            fresh_state.add_user_message(str(i))
        assert (
            len(fresh_state.get_reasoning_context()) == DEFAULT_REASONING_CONTEXT_SIZE
        )


class TestAgentStateGeneratedBy:
    def test_generated_by_unknown_when_pipeline_empty(self, fresh_state: AgentState):
        fresh_state.add_assistant_message("hi")
        assert fresh_state.conversation.messages[-1].generated_by == "unknown"

    def test_generated_by_single_anthropic_model(self, fresh_state: AgentState):
        fresh_state.cognitive.generation_pipeline = ["claude-sonnet-4-5"]
        fresh_state.add_assistant_message("hi")
        assert fresh_state.conversation.messages[-1].generated_by == "anthropic"

    def test_generated_by_single_non_anthropic_model(self, fresh_state: AgentState):
        fresh_state.cognitive.generation_pipeline = ["llama31"]
        fresh_state.add_assistant_message("hi")
        assert fresh_state.conversation.messages[-1].generated_by == "llama31"

    def test_generated_by_mixed_when_multiple_providers(self, fresh_state: AgentState):
        fresh_state.cognitive.generation_pipeline = ["claude-sonnet-4-5", "llama31"]
        fresh_state.add_assistant_message("hi")
        assert fresh_state.conversation.messages[-1].generated_by == "mixed"

    def test_generated_by_not_mixed_when_all_anthropic(self, fresh_state: AgentState):
        # Both map to the same "anthropic" label, so this should NOT be "mixed".
        fresh_state.cognitive.generation_pipeline = [
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
        ]
        fresh_state.add_assistant_message("hi")
        assert fresh_state.conversation.messages[-1].generated_by == "anthropic"


class TestAgentStateTraceAndLastNode:
    def test_last_node_none_when_no_trace(self, fresh_state: AgentState):
        assert fresh_state.last_node is None

    def test_last_node_returns_most_recent(self, fresh_state: AgentState):
        fresh_state.add_trace("thought", "react_reasoner")
        fresh_state.add_trace("tool_execution", "tool_executor")
        assert fresh_state.last_node == "tool_executor"


class TestAgentStateSerialize:
    def test_serialize_datetime(self, fresh_state: AgentState):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        assert fresh_state._serialize(dt) == dt.isoformat()

    def test_serialize_enum_uses_value(self, fresh_state: AgentState):
        assert (
            fresh_state._serialize(AgentState.WaitingFor.PROBLEM_INPUT)
            == "PROBLEM_INPUT"
        )

    def test_serialize_exception_as_string(self, fresh_state: AgentState):
        err = ValueError("boom")
        assert fresh_state._serialize(err) == "boom"

    def test_serialize_set_is_sorted_list(self, fresh_state: AgentState):
        assert fresh_state._serialize({"b", "a", "c"}) == ["a", "b", "c"]

    def test_serialize_nested_list_and_dict(self, fresh_state: AgentState):
        data = {"a": [1, 2, {"b": datetime(2024, 1, 1)}]}
        result = fresh_state._serialize(data)
        assert result["a"][0] == 1
        assert result["a"][2]["b"] == datetime(2024, 1, 1).isoformat()

    def test_serialize_dataclass_recurses_fields(self, fresh_state: AgentState):
        step = ReActStep(thought="t", tool_name="tool1", tool_arguments={"x": 1})
        result = fresh_state._serialize(step)
        assert result["thought"] == "t"
        assert result["tool_name"] == "tool1"
        assert result["tool_arguments"] == {"x": 1}

    def test_serialize_falls_back_to_repr_for_unjsonable_object(
        self, fresh_state: AgentState
    ):
        class Unserializable:
            def __repr__(self):
                return "<Unserializable obj>"

        result = fresh_state._serialize(Unserializable())
        assert result == "<Unserializable obj>"

    def test_serialize_json_native_passthrough(self, fresh_state: AgentState):
        assert fresh_state._serialize("plain string") == "plain string"
        assert fresh_state._serialize(42) == 42
        assert fresh_state._serialize(None) is None

    def test_dump_to_file_produces_valid_json(self, fresh_state: AgentState, tmp_path):
        fresh_state.add_user_message("hello")
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        filepath = tmp_path / "state.json"

        import os as _os

        cwd = _os.getcwd()
        _os.chdir(tmp_path)
        try:
            fresh_state.dump_to_file(str(filepath))
        finally:
            _os.chdir(cwd)

        with open(filepath, encoding="utf-8") as f:
            dumped = json.load(f)

        assert dumped["session_id"] == "test-session"
        assert dumped["waiting_for"] == "PROBLEM_CONFIRMATION"
        assert dumped["conversation"]["messages"][0]["content"] == "hello"

    def test_dump_to_file_compacts_actions_and_omits_retrieved_trace_data(
        self, fresh_state: AgentState, tmp_path
    ):
        fresh_state.assistant_action_data = [
            {
                "type": "map",
                "widgetName": "territorial-index",
                "data": {"large": "payload"},
            },
            {"type": "plot", "data": [1, 2, 3]},
        ]
        fresh_state.add_trace(
            "diagnostic",
            "test_node",
            {
                "result_key": "lookup",
                "nested": {"retrieved": {"large": "payload"}},
            },
        )
        filepath = tmp_path / "state.json"

        import os as _os

        cwd = _os.getcwd()
        _os.chdir(tmp_path)
        try:
            fresh_state.dump_to_file(str(filepath))
        finally:
            _os.chdir(cwd)

        with open(filepath, encoding="utf-8") as f:
            dumped = json.load(f)

        assert dumped["assistant_action_data"] == [
            {"type": "map", "widgetName": "territorial-index"},
            {"type": "plot"},
        ]
        assert dumped["cognitive"]["trace"]["steps"][0]["data"] == {
            "result_key": "lookup",
            "nested": {},
        }
        # File sanitization must not mutate the live state used by the agent.
        assert "data" in fresh_state.assistant_action_data[0]
        assert "retrieved" in fresh_state.cognitive.trace.steps[0].data["nested"]
