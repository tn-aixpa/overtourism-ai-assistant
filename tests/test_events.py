import json

import pytest

from app.agent import events


@pytest.fixture(autouse=True)
def _clean_queues():
    events._queues.clear()
    events._results.clear()
    yield
    events._queues.clear()
    events._results.clear()


class TestPublish:
    def test_publish_pushes_raw_string_onto_queue(self):
        events.publish("s1", "raw-event")
        q = events.get_queue("s1")
        assert q.get_nowait() == "raw-event"

    def test_get_queue_creates_queue_for_new_session(self):
        q = events.get_queue("brand-new-session")
        assert q.empty()


class TestPublishThought:
    def test_publishes_json_with_type_thought(self):
        events.publish_thought("s1", "I should look up the glossary")
        q = events.get_queue("s1")
        payload = json.loads(q.get_nowait())
        assert payload == {
            "type": "thought",
            "content": "I should look up the glossary",
        }


class TestPublishAction:
    def test_publishes_json_with_type_action(self):
        events.publish_action("s1", "lookup_glossary")
        q = events.get_queue("s1")
        payload = json.loads(q.get_nowait())
        assert payload == {"type": "action", "tool": "lookup_glossary"}


class TestPublishDoneAndGetResult:
    def test_publish_done_stores_result_and_signals_queue(self):
        events.publish_done("s1", {"answer": "42"})
        assert events.get_result("s1") == {"answer": "42"}
        q = events.get_queue("s1")
        assert q.get_nowait() == "__done__"

    def test_get_result_is_idempotent_for_retries(self):
        events.publish_done("s1", {"answer": "42"})
        assert events.get_result("s1") == {"answer": "42"}
        assert events.get_result("s1") == {"answer": "42"}

    def test_get_result_returns_copy_of_stored_result(self):
        events.publish_done("s1", {"answer": "42"})
        result = events.get_result("s1")
        result["answer"] = "changed"
        assert events.get_result("s1") == {"answer": "42"}

    def test_get_result_missing_session_returns_none(self):
        assert events.get_result("never-published") is None


class TestClearSession:
    def test_clears_queue_and_result(self):
        events.publish_thought("s1", "hi")
        events.publish_done("s1", {"x": 1})

        events.clear_session("s1")

        assert "s1" not in events._queues
        assert "s1" not in events._results

    def test_clear_missing_session_is_noop(self):
        events.clear_session("never-existed")  # should not raise

    def test_ordering_of_multiple_events_preserved(self):
        events.publish_thought("s1", "first")
        events.publish_action("s1", "some_tool")
        events.publish_thought("s1", "second")

        q = events.get_queue("s1")
        first = json.loads(q.get_nowait())
        second = json.loads(q.get_nowait())
        third = json.loads(q.get_nowait())

        assert first["content"] == "first"
        assert second["tool"] == "some_tool"
        assert third["content"] == "second"
