import asyncio
import json
import threading
import time

import pytest

from app.agent import events


@pytest.fixture(autouse=True)
def _fresh_event_store(monkeypatch):
    monkeypatch.setattr(events, "store", events.TurnStore())


def start_turn(session_id="s1"):
    turn_id, created = events.store.start_turn(session_id)
    assert created
    return turn_id


class TestTurnStore:
    def test_start_turn_records_active_and_latest_turn(self):
        turn_id = start_turn()

        assert events.store.active_turn("s1") == turn_id
        assert events.store.latest_turn("s1") == turn_id
        assert events.store.get(turn_id) == {
            "turn_id": turn_id,
            "session_id": "s1",
            "status": "running",
            "last_event_id": 0,
            "result": None,
        }

    def test_idempotency_key_reuses_turn(self):
        turn_id, created = events.store.start_turn("s1", "request-1")

        replay_id, replay_created = events.store.start_turn("s1", "request-1")

        assert (replay_id, replay_created) == (turn_id, False)

    def test_rejects_a_second_active_turn_for_session(self):
        from app.agent.events import TurnInProgress

        turn_id = start_turn()

        with pytest.raises(TurnInProgress) as exc_info:
            events.store.start_turn("s1")

        assert exc_info.value.turn_id == turn_id

    def test_append_event_assigns_increasing_ids_and_is_non_consuming(self):
        turn_id = start_turn()

        assert events.store.append_event(turn_id, '{"n": 1}') == 1
        assert events.store.append_event(turn_id, '{"n": 2}') == 2
        assert events.store.read_events(turn_id, 0) == (
            [(1, '{"n": 1}'), (2, '{"n": 2}')],
            "running",
        )
        assert events.store.read_events(turn_id, 1) == ([(2, '{"n": 2}')], "running")
        assert events.store.read_events(turn_id, 0) == (
            [(1, '{"n": 1}'), (2, '{"n": 2}')],
            "running",
        )

    def test_finish_is_first_writer_wins_and_releases_session(self):
        turn_id = start_turn()

        assert events.store.finish(turn_id, "done", {"response": "ok"})
        assert not events.store.finish(turn_id, "failed", {"response": "error"})
        assert events.store.active_turn("s1") is None
        assert events.store.get(turn_id)["result"] == {"response": "ok"}

    def test_append_after_finish_is_dropped(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "done", {"response": "ok"})

        assert events.store.append_event(turn_id, '{"late": true}') is None

    def test_result_is_copied_on_read(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "done", {"response": "ok"})

        result = events.store.get(turn_id)["result"]
        result["response"] = "changed"

        assert events.store.get(turn_id)["result"] == {"response": "ok"}

    def test_clear_session_removes_turns_and_active_reference(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, "{}")

        events.clear_session("s1")

        assert events.store.get(turn_id) is None
        assert events.store.active_turn("s1") is None
        assert events.store.latest_turn("s1") is None

    def test_start_turn_without_key_never_replays(self):
        first = start_turn()
        events.store.finish(first, "done", None)

        second, created = events.store.start_turn("s1")

        assert created and second != first

    def test_idempotency_key_is_scoped_per_session(self):
        a, _ = events.store.start_turn("s1", "k")
        b, created = events.store.start_turn("s2", "k")

        assert created and a != b

    def test_idempotency_key_replays_even_after_the_turn_finished(self):
        turn_id, _ = events.store.start_turn("s1", "k")
        events.store.finish(turn_id, "done", {"response": "ok"})

        replay, created = events.store.start_turn("s1", "k")

        assert (replay, created) == (turn_id, False)

    def test_idempotent_replay_wins_over_the_in_progress_check(self):
        """A retry of the SAME request must get its turn back, not a 409."""
        turn_id, _ = events.store.start_turn("s1", "k")

        replay, created = events.store.start_turn("s1", "k")

        assert (replay, created) == (turn_id, False)

    def test_new_key_while_running_is_rejected(self):
        from app.agent.events import TurnInProgress

        events.store.start_turn("s1", "k1")

        with pytest.raises(TurnInProgress):
            events.store.start_turn("s1", "k2")

    def test_new_turn_allowed_after_previous_one_finished(self):
        first = start_turn()
        events.store.finish(first, "failed", None)

        second, created = events.store.start_turn("s1")

        assert created and second != first
        assert events.store.active_turn("s1") == second
        assert events.store.latest_turn("s1") == second
        # the old turn is still readable
        assert events.store.get(first)["status"] == "failed"

    def test_sessions_are_independent(self):
        a = start_turn("s1")
        b = start_turn("s2")

        assert events.store.active_turn("s1") == a
        assert events.store.active_turn("s2") == b
        events.store.append_event(a, "{}")
        assert events.store.read_events(b, 0) == ([], "running")

    @pytest.mark.parametrize("status", ["done", "failed", "timeout"])
    def test_every_terminal_status_is_accepted(self, status):
        turn_id = start_turn()

        assert events.store.finish(turn_id, status, {"r": 1})
        assert events.store.get(turn_id)["status"] == status

    @pytest.mark.parametrize("status", ["running", "weird", "", "DONE"])
    def test_finish_rejects_non_terminal_statuses(self, status):
        turn_id = start_turn()

        with pytest.raises(ValueError):
            events.store.finish(turn_id, status, None)

        assert events.store.get(turn_id)["status"] == "running"

    def test_finish_unknown_turn_returns_false(self):
        assert events.store.finish("nope", "done", None) is False

    def test_finish_with_no_result_is_allowed(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "done", None)

        assert events.store.get(turn_id)["result"] is None

    def test_before_commit_runs_for_the_winner_only(self):
        turn_id = start_turn()
        calls = []

        assert events.store.finish(turn_id, "timeout", None, before_commit=lambda: calls.append("a"))
        assert not events.store.finish(turn_id, "done", None, before_commit=lambda: calls.append("b"))

        assert calls == ["a"]

    def test_before_commit_sees_a_still_running_turn_and_a_busy_session(self):
        """It must run BEFORE the turn becomes terminal / the session is freed,
        so the next turn can never load a stale state."""
        turn_id = start_turn()
        seen = {}

        def hook():
            seen["status"] = events.store.get(turn_id)["status"]
            seen["active"] = events.store.active_turn("s1")

        events.store.finish(turn_id, "done", None, before_commit=hook)

        assert seen == {"status": "running", "active": turn_id}
        assert events.store.active_turn("s1") is None

    def test_failing_before_commit_leaves_the_turn_untouched(self):
        turn_id = start_turn()

        def boom():
            raise RuntimeError("remember_state failed")

        with pytest.raises(RuntimeError):
            events.store.finish(turn_id, "done", {"response": "x"}, before_commit=boom)

        snap = events.store.get(turn_id)
        assert snap["status"] == "running" and snap["result"] is None
        assert events.store.active_turn("s1") == turn_id
        # ... so the caller can still close it as failed
        assert events.store.finish(turn_id, "failed", {"response": "System error"})

    def test_finishing_an_old_turn_does_not_release_a_newer_active_turn(self):
        """Defensive: _active[session] is only cleared if it still points at the
        turn being finished."""
        old = start_turn()
        events.store._active["s1"] = "someone-else"

        events.store.finish(old, "done", None)

        assert events.store.active_turn("s1") == "someone-else"

    def test_append_event_to_unknown_turn_is_dropped(self):
        assert events.store.append_event("nope", "{}") is None

    def test_read_events_unknown_turn_is_none(self):
        assert events.store.read_events("nope", 0) is None

    def test_read_events_negative_cursor_is_treated_as_zero(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, "a")

        assert events.store.read_events(turn_id, -10) == ([(1, "a")], "running")

    def test_read_events_cursor_past_the_end_is_empty(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, "a")

        assert events.store.read_events(turn_id, 5) == ([], "running")

    def test_read_events_reports_terminal_status_with_the_events(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, "a")
        events.store.finish(turn_id, "done", None)

        assert events.store.read_events(turn_id, 0) == ([(1, "a")], "done")
        assert events.store.read_events(turn_id, 1) == ([], "done")

    def test_get_reports_last_event_id(self):
        turn_id = start_turn()
        for i in range(3):
            events.store.append_event(turn_id, str(i))

        assert events.store.get(turn_id)["last_event_id"] == 3

    def test_get_unknown_turn_is_none(self):
        assert events.store.get("nope") is None

    def test_clear_session_only_touches_that_session(self):
        a = start_turn("s1")
        b = start_turn("s2")

        events.clear_session("s1")

        assert events.store.get(a) is None
        assert events.store.get(b) is not None
        assert events.store.active_turn("s2") == b

    def test_clear_session_forgets_idempotency_keys(self):
        old, _ = events.store.start_turn("s1", "k")
        events.clear_session("s1")

        new, created = events.store.start_turn("s1", "k")

        assert created and new != old

    def test_clear_session_makes_late_writes_noops(self):
        turn_id = start_turn()
        events.clear_session("s1")

        assert events.store.append_event(turn_id, "{}") is None
        assert events.store.finish(turn_id, "done", {"r": 1}) is False

    def test_clear_unknown_session_is_a_noop(self):
        events.clear_session("never-existed")

    def test_latest_turn_survives_finish(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "done", None)

        assert events.store.latest_turn("s1") == turn_id
        assert events.store.active_turn("s1") is None

    def test_unknown_session_has_no_turns(self):
        assert events.store.active_turn("x") is None
        assert events.store.latest_turn("x") is None


class TestTtlSweep:
    @pytest.fixture(autouse=True)
    def _short_ttl(self, monkeypatch):
        monkeypatch.setattr(events, "TURN_TTL_SECONDS", 0.05)

    def test_finished_turns_are_swept_after_the_ttl(self):
        turn_id, _ = events.store.start_turn("s1", "k")
        events.store.finish(turn_id, "done", {"r": 1})
        time.sleep(0.1)

        events.store.start_turn("s2")  # any start_turn triggers the sweep

        assert events.store.get(turn_id) is None
        assert events.store.latest_turn("s1") is None

    def test_swept_idempotency_key_starts_a_fresh_turn(self):
        old, _ = events.store.start_turn("s1", "k")
        events.store.finish(old, "done", None)
        time.sleep(0.1)

        new, created = events.store.start_turn("s1", "k")

        assert created and new != old

    def test_running_turns_are_never_swept(self):
        turn_id = start_turn("s1")
        time.sleep(0.1)

        events.store.start_turn("s2")

        assert events.store.get(turn_id)["status"] == "running"

    def test_recently_finished_turns_survive(self, monkeypatch):
        monkeypatch.setattr(events, "TURN_TTL_SECONDS", 60)
        turn_id = start_turn()
        events.store.finish(turn_id, "done", None)

        events.store.start_turn("s2")

        assert events.store.get(turn_id) is not None

    def test_sweeping_a_stream_target_yields_gone(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "done", None)
        time.sleep(0.1)
        events.store.start_turn("s2")

        frames = asyncio.run(_collect_sse(turn_id))

        assert json.loads(frames[-1].split("data: ", 1)[1]) == {"status": "gone"}


class TestConcurrency:
    def test_concurrent_start_turn_for_one_session_admits_exactly_one(self):
        from app.agent.events import TurnInProgress

        wins, losses = [], []

        def attempt():
            try:
                wins.append(events.store.start_turn("s1")[0])
            except TurnInProgress:
                losses.append(1)

        threads = [threading.Thread(target=attempt) for _ in range(50)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert len(wins) == 1 and len(losses) == 49

    def test_concurrent_finish_has_a_single_winner(self):
        turn_id = start_turn()
        results = []

        def attempt(status):
            results.append(events.store.finish(turn_id, status, {"s": status}))

        threads = [
            threading.Thread(target=attempt, args=(st,))
            for st in ["done", "failed", "timeout"] * 10
        ]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert results.count(True) == 1
        snap = events.store.get(turn_id)
        assert snap["result"] == {"s": snap["status"]}

    def test_concurrent_appends_get_unique_contiguous_ids(self):
        turn_id = start_turn()
        ids = []

        def append(i):
            ids.append(events.store.append_event(turn_id, str(i)))

        threads = [threading.Thread(target=append, args=(i,)) for i in range(100)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert sorted(ids) == list(range(1, 101))
        entries, _ = events.store.read_events(turn_id, 0)
        assert [seq for seq, _ in entries] == list(range(1, 101))


class TestPublishing:
    def test_action_is_published_to_the_active_turn(self):
        turn_id = start_turn()

        events.publish_action("s1", "lookup_glossary")

        entries, status = events.store.read_events(turn_id, 0)
        assert status == "running"
        assert json.loads(entries[0][1]) == {
            "type": "action",
            "tool": "lookup_glossary",
        }

    def test_thought_is_not_published(self):
        turn_id = start_turn()

        events.publish_thought("s1", "private reasoning")

        assert events.store.read_events(turn_id, 0) == ([], "running")

    def test_action_without_active_turn_is_ignored(self):
        events.publish_action("unknown-session", "lookup_glossary")

        assert events.store.latest_turn("unknown-session") is None

    def test_action_payload_is_compact_json_with_unicode_preserved(self):
        turn_id = start_turn()

        events.publish_action("s1", "strumento-è-日本")

        payload = events.store.read_events(turn_id, 0)[0][0][1]
        assert "strumento-è-日本" in payload  # ensure_ascii=False
        assert json.loads(payload) == {"type": "action", "tool": "strumento-è-日本"}

    def test_action_after_the_turn_finished_is_dropped(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "timeout", None)

        events.publish_action("s1", "late_tool")

        assert events.store.read_events(turn_id, 0) == ([], "timeout")

    def test_turn_context_binds_the_turn_even_if_the_session_moved_on(self):
        """A zombie thread keeps publishing into ITS turn (where it is dropped)
        and never into the session's newer, active turn."""
        old = start_turn()
        events.store.finish(old, "timeout", None)
        new = start_turn()

        with events.turn_context(old):
            events.publish_action("s1", "zombie_tool")

        assert events.store.read_events(new, 0) == ([], "running")
        assert events.store.read_events(old, 0) == ([], "timeout")

    def test_turn_context_is_reset_on_exit(self):
        turn_id = start_turn()

        with events.turn_context("bound-turn"):
            assert events._current_turn.get() == "bound-turn"
        assert events._current_turn.get() is None

        # without a bound turn the session's active turn is used
        events.publish_action("s1", "tool")
        assert events.store.read_events(turn_id, 0)[0][0][0] == 1

    def test_turn_context_is_reset_even_when_the_body_raises(self):
        with pytest.raises(RuntimeError):
            with events.turn_context("t"):
                raise RuntimeError("boom")

        assert events._current_turn.get() is None

    def test_turn_context_is_isolated_between_threads(self):
        a, b = start_turn("sa"), start_turn("sb")

        def worker(turn_id, session_id, tool):
            with events.turn_context(turn_id):
                events.publish_action(session_id, tool)

        threads = [
            threading.Thread(target=worker, args=(a, "sa", "tool_a")),
            threading.Thread(target=worker, args=(b, "sb", "tool_b")),
        ]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert json.loads(events.store.read_events(a, 0)[0][0][1])["tool"] == "tool_a"
        assert json.loads(events.store.read_events(b, 0)[0][0][1])["tool"] == "tool_b"

    def test_session_fallback_is_used_when_the_context_did_not_propagate(self):
        """LangGraph may run a node in its own worker thread: the ContextVar is
        then unset, and publish_action falls back to the active turn."""
        turn_id = start_turn()
        done = threading.Event()

        def node_in_worker_thread():
            events.publish_action("s1", "from_worker")
            done.set()

        threading.Thread(target=node_in_worker_thread).start()
        assert done.wait(2)

        assert json.loads(events.store.read_events(turn_id, 0)[0][0][1])["tool"] == "from_worker"

    def test_clear_session_helper_delegates_to_the_store(self):
        turn_id = start_turn()

        events.clear_session("s1")

        assert events.store.get(turn_id) is None


class TestSse:
    def test_terminal_turn_emits_events_then_done(self):
        turn_id = start_turn()
        events.store.append_event(
            turn_id,
            json.dumps({"type": "action", "tool": "lookup_glossary"}),
        )
        events.store.finish(turn_id, "done", {"response": "ok"})

        frames = asyncio.run(_collect_sse(turn_id))

        assert len(frames) == 3
        assert frames[0] == "retry: 2000\n\n"
        assert "event: status" in frames[1]
        assert "id: 1" in frames[1]
        assert json.loads(frames[1].split("data: ", 1)[1]) == {
            "type": "action",
            "tool": "lookup_glossary",
        }
        assert "event: done" in frames[2]
        assert json.loads(frames[2].split("data: ", 1)[1]) == {"status": "done"}

    def test_unknown_turn_emits_gone(self):
        frames = asyncio.run(_collect_sse("missing-turn"))

        assert len(frames) == 2
        assert frames[0] == "retry: 2000\n\n"
        assert "event: done" in frames[1]
        assert json.loads(frames[1].split("data: ", 1)[1]) == {"status": "gone"}

    def test_after_cursor_does_not_repeat_prior_events(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, '{"n": 1}')
        events.store.append_event(turn_id, '{"n": 2}')
        events.store.finish(turn_id, "done", None)

        frames = asyncio.run(_collect_sse(turn_id, after=1))

        assert len(frames) == 3
        assert "id: 2" in frames[1]
        assert '{"n": 2}' in frames[1]

    def test_sse_frame_format(self):
        assert events._sse("status", "{}", 7) == "id: 7\nevent: status\ndata: {}\n\n"
        assert events._sse("done", "{}") == "event: done\ndata: {}\n\n"

    def test_done_frame_id_is_one_past_the_last_event(self):
        turn_id = start_turn()
        for i in range(3):
            events.store.append_event(turn_id, "{}")
        events.store.finish(turn_id, "done", None)

        frames = asyncio.run(_collect_sse(turn_id))

        assert "id: 4" in frames[-1]

    def test_done_frame_without_events_has_id_one(self):
        turn_id = start_turn()
        events.store.finish(turn_id, "failed", None)

        frames = asyncio.run(_collect_sse(turn_id))

        assert frames[1].startswith("id: 1\nevent: done")
        assert json.loads(frames[1].split("data: ", 1)[1]) == {"status": "failed"}

    @pytest.mark.parametrize("status", ["done", "failed", "timeout"])
    def test_done_frame_carries_the_terminal_status(self, status):
        turn_id = start_turn()
        events.store.finish(turn_id, status, None)

        frames = asyncio.run(_collect_sse(turn_id))

        assert json.loads(frames[-1].split("data: ", 1)[1]) == {"status": status}

    def test_negative_after_is_treated_as_zero(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, '{"n": 1}')
        events.store.finish(turn_id, "done", None)

        frames = asyncio.run(_collect_sse(turn_id, after=-3))

        assert "id: 1" in frames[1]

    def test_after_beyond_the_end_only_emits_done(self):
        turn_id = start_turn()
        events.store.append_event(turn_id, "{}")
        events.store.finish(turn_id, "done", None)

        frames = asyncio.run(_collect_sse(turn_id, after=50))

        assert len(frames) == 2 and "event: done" in frames[1]

    def test_stream_waits_for_a_running_turn_and_ends_when_it_finishes(self):
        turn_id = start_turn()

        async def scenario():
            frames = []

            async def reader():
                async for f in events.iter_sse(turn_id, poll_interval=0.005, keepalive_every=5):
                    frames.append(f)

            task = asyncio.create_task(reader())
            await asyncio.sleep(0.05)
            events.store.append_event(turn_id, '{"n": 1}')
            await asyncio.sleep(0.05)
            events.store.append_event(turn_id, '{"n": 2}')
            await asyncio.sleep(0.05)
            assert not task.done(), "stream must stay open while the turn runs"
            events.store.finish(turn_id, "done", None)
            await asyncio.wait_for(task, 2)
            return frames

        frames = asyncio.run(scenario())

        assert [f.split("\n")[1] for f in frames[1:]] == [
            "event: status",
            "event: status",
            "event: done",
        ]

    def test_keepalive_comment_is_emitted_while_idle(self):
        turn_id = start_turn()

        async def scenario():
            gen = events.iter_sse(turn_id, poll_interval=0.01, keepalive_every=0.03)
            frames = []
            async for frame in gen:
                frames.append(frame)
                if frame.startswith(": keep-alive"):
                    break
            await gen.aclose()
            return frames

        frames = asyncio.run(scenario())

        assert frames[0] == "retry: 2000\n\n"
        assert frames[-1] == ": keep-alive\n\n"

    def test_events_reset_the_keepalive_timer(self):
        turn_id = start_turn()

        async def scenario():
            frames = []

            async def reader():
                async for f in events.iter_sse(turn_id, poll_interval=0.01, keepalive_every=0.2):
                    frames.append(f)

            task = asyncio.create_task(reader())
            for _ in range(6):  # steady traffic, faster than the keep-alive period
                await asyncio.sleep(0.05)
                events.store.append_event(turn_id, "{}")
            events.store.finish(turn_id, "done", None)
            await asyncio.wait_for(task, 2)
            return frames

        assert not any(f.startswith(": keep-alive") for f in asyncio.run(scenario()))

    def test_stream_can_be_cancelled_cleanly_by_a_disconnecting_client(self):
        turn_id = start_turn()

        async def scenario():
            async def reader():
                async for _ in events.iter_sse(turn_id, poll_interval=0.005):
                    pass

            task = asyncio.create_task(reader())
            await asyncio.sleep(0.03)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())

    def test_reset_while_streaming_ends_with_gone(self):
        turn_id = start_turn()

        async def scenario():
            frames = []

            async def reader():
                async for f in events.iter_sse(turn_id, poll_interval=0.005):
                    frames.append(f)

            task = asyncio.create_task(reader())
            await asyncio.sleep(0.03)
            events.clear_session("s1")
            await asyncio.wait_for(task, 2)
            return frames

        frames = asyncio.run(scenario())

        assert json.loads(frames[-1].split("data: ", 1)[1]) == {"status": "gone"}

    def test_two_readers_of_one_turn_get_identical_frames(self):
        turn_id = start_turn()
        for i in range(4):
            events.store.append_event(turn_id, json.dumps({"n": i}))
        events.store.finish(turn_id, "done", None)

        a = asyncio.run(_collect_sse(turn_id))
        b = asyncio.run(_collect_sse(turn_id))

        assert a == b and len(a) == 6


async def _collect_sse(turn_id, after=0):
    frames = []
    async for frame in events.iter_sse(
        turn_id, after=after, poll_interval=0.001, keepalive_every=1
    ):
        frames.append(frame)
    return frames
