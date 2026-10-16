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
        queue = events.get_queue("s1")

        events.clear_session("s1")

        # Streams may already hold a reference to the session queue, so clear
        # its contents without replacing or removing the queue itself.
        assert events.get_queue("s1") is queue
        assert queue.empty()
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


# ---------------------------------------------------------------------------
# Added: concurrency / turn-boundary behaviour of the event bus
# ---------------------------------------------------------------------------
import threading
import time
from queue import Empty


class TestBeginTurn:
    def test_drops_stale_done_and_stale_result(self):
        events.publish_thought("s1", "old thought")
        events.publish_done("s1", {"answer": "OLD"})
        assert events.has_result("s1")

        events.begin_turn("s1")

        assert not events.has_result("s1")
        assert events.get_result("s1") is None
        assert events.get_queue("s1").empty()

    def test_leaves_other_sessions_untouched(self):
        events.publish_done("other", {"answer": "keep me"})
        events.publish_done("s1", {"answer": "old"})
        events.begin_turn("s1")
        assert events.get_result("other") == {"answer": "keep me"}
        assert events.get_queue("other").get_nowait() == "__done__"

    def test_is_safe_for_a_session_never_seen_before(self):
        events.begin_turn("brand-new")
        assert not events.has_result("brand-new")


class TestHasResult:
    def test_false_until_publish_done(self):
        assert not events.has_result("s1")
        events.publish_thought("s1", "thinking")
        assert not events.has_result("s1")
        events.publish_done("s1", {"a": 1})
        assert events.has_result("s1")


class TestEventJsonIsSseSafe:
    @pytest.mark.parametrize(
        "text", ["a\nb", "a\r\nb", "a\n\nevent: done\ndata: ", "tab\there", "\u2028"]
    )
    def test_thought_payload_has_no_raw_line_breaks(self, text):
        """routes.py frames events as 'data: {event}\\n\\n'; a raw newline inside
        the payload would split/forge SSE frames."""
        events.publish_thought("s1", text)
        raw = events.get_queue("s1").get_nowait()
        assert "\n" not in raw and "\r" not in raw
        assert json.loads(raw)["content"] == text

    def test_non_ascii_is_kept_readable(self):
        events.publish_thought("s1", "è 日本")
        raw = events.get_queue("s1").get_nowait()
        assert "è 日本" in raw  # ensure_ascii=False

    def test_non_json_serialisable_content_does_not_raise(self):
        events.publish_thought("s1", object())  # default=str
        assert json.loads(events.get_queue("s1").get_nowait())["type"] == "thought"


class TestConcurrency:
    def test_parallel_publishers_lose_nothing_and_keep_per_session_order(self):
        n_threads, n_events = 16, 400

        def producer(i):
            for k in range(n_events):
                events.publish_thought(f"s{i}", f"{k}")

        ts = [threading.Thread(target=producer, args=(i,)) for i in range(n_threads)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        for i in range(n_threads):
            q = events.get_queue(f"s{i}")
            got = [json.loads(q.get_nowait())["content"] for _ in range(n_events)]
            assert got == [str(k) for k in range(n_events)]
            assert q.empty()

    def test_result_is_always_visible_once_done_is_observable(self):
        """publish_done must store the result BEFORE queueing '__done__'."""
        violations = []
        for round_ in range(300):
            sid = f"s{round_}"
            seen = threading.Event()

            def consumer():
                q = events.get_queue(sid)
                while True:
                    try:
                        if q.get_nowait() == "__done__":
                            if events.get_result(sid) is None:
                                violations.append(sid)
                            seen.set()
                            return
                    except Empty:
                        time.sleep(0)

            t = threading.Thread(target=consumer)
            t.start()
            events.publish_done(sid, {"n": round_})
            assert seen.wait(2)
            t.join()
        assert not violations

    def test_two_consumers_split_events_without_duplicates(self):
        """Documents the competing-consumer behaviour that makes a second SSE
        connection on the same session steal events from the first."""
        for i in range(200):
            events.publish_thought("s1", str(i))
        q = events.get_queue("s1")
        taken = {"a": [], "b": []}

        def consume(name):
            while True:
                try:
                    taken[name].append(json.loads(q.get_nowait())["content"])
                except Empty:
                    return

        ts = [threading.Thread(target=consume, args=(n,)) for n in taken]
        [t.start() for t in ts]
        [t.join() for t in ts]
        everything = taken["a"] + taken["b"]
        assert sorted(everything, key=int) == [str(i) for i in range(200)]
        assert len(set(everything)) == 200

    def test_get_result_is_thread_safe_against_concurrent_publish_done(self):
        stop = threading.Event()
        errors = []

        def writer():
            n = 0
            while not stop.is_set():
                events.publish_done("s1", {"n": n})
                n += 1

        def reader():
            while not stop.is_set():
                try:
                    r = events.get_result("s1")
                    assert r is None or "n" in r
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

        ts = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(3)]
        [t.start() for t in ts]
        time.sleep(0.3)
        stop.set()
        [t.join() for t in ts]
        assert not errors


class TestStaleEventsAfterClear:
    def test_events_published_after_clear_session_still_reach_the_queue(self):
        """clear_session() keeps the queue object alive on purpose (streams hold a
        reference). A late publish - e.g. from a turn thread that outlived a reset
        or a watchdog timeout - therefore lands in the live queue. Nothing in
        events.py can tell it apart from a current event: see
        test_sse_lifecycle.py::TestWatchdog for the user-visible consequence."""
        q = events.get_queue("s1")
        events.clear_session("s1")
        events.publish_thought("s1", "late zombie thought")
        assert json.loads(q.get_nowait())["content"] == "late zombie thought"
