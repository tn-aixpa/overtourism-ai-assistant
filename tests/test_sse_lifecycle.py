"""
End-to-end SSE contract tests (real uvicorn + real routes/events/memory).

The contract the frontend relies on, for EVERY turn, whatever happens inside it:

    POST /agent                         -> 202 {session_id, turn_id}
    GET  /agent/turns/{turn_id}/events  -> zero or more `status` events (SSE
                                           `id:` = 1, 2, 3 ...), then exactly
                                           one `done`, then the stream closes
    GET  /agent/turns/{turn_id}         -> {status, last_event_id, result}
                                           (result = the answer of THIS turn)

Design rules these tests pin down (see app/agent/events.py):

* events are never consumed - a reader keeps a cursor (Last-Event-ID)
* a turn is terminal once status != "running"; finish() is first-wins
* a stream ends when ITS turn is terminal, not when "the session has a result"
* a late / zombie agent thread cannot write into a terminal (or reset) turn
* POST /agent is idempotent per (session, Idempotency-Key)
"""

from __future__ import annotations

import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from sse_harness import (
    AUTH,
    action,
    auth_for,
    call,
    get_turn,
    hang,
    parse_sse_frames,
    post_turn,
    raise_,
    read_stream,
    run_turn,
    seed_session,
    sleep,
    sse_lines,
    wait_for_status,
)
from app.agent import events, memory


# --------------------------------------------------------------------------- #
# Basic shape of a turn
# --------------------------------------------------------------------------- #
class TestHappyPath:
    @pytest.mark.parametrize(
        ("force_role", "expected_role"),
        [(None, None), ("auto", None), ("operative", "operative")],
    )
    def test_force_role_form_is_optional_and_saved_for_the_turn(
        self, live, force_role, expected_role
    ):
        extra_form = {} if force_role is None else {"force_role": force_role}

        rec = run_turn(
            live.base,
            f"force-role-{force_role or 'omitted'}",
            "hello",
            extra_form=extra_form,
        )

        assert rec.post_status == 202, rec.error
        assert live.routes.load_state(rec.session).force_role == expected_role

    def test_force_role_rejects_unknown_values(self, live):
        rec = run_turn(
            live.base, "force-role-invalid", "hello", extra_form={"force_role": "unknown"}
        )

        assert rec.post_status == 422

    def test_post_returns_session_and_turn_ids(self, live):
        r = post_turn(live.base, "s1", "hello")

        assert r.status_code == 202
        body = r.json()
        assert body["session_id"] == "s1"
        assert body["turn_id"] and isinstance(body["turn_id"], str)

    def test_events_are_published_in_order_then_exactly_one_done(self, live):
        live.agent.script_for = lambda sid, m: [action("tool_a"), action("tool_b")]

        rec = run_turn(live.base, "s1", "hello")

        assert rec.error is None
        assert rec.statuses == [
            {"type": "action", "tool": "tool_a"},
            {"type": "action", "tool": "tool_b"},
        ]
        names = [n for _, n, _ in rec.sse_events]
        assert names.count("done") == 1 and names[-1] == "done"
        assert rec.done_payload == {"status": "done"}
        assert rec.result["response"] == "answer-to:hello"

    def test_event_ids_are_sequential_and_done_follows_the_last_one(self, live):
        live.agent.script_for = lambda sid, m: [action(f"t{i}") for i in range(5)]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]

        frames = read_stream(live.base, turn_id)

        assert [(i, n) for i, n, _ in frames] == [
            (1, "status"),
            (2, "status"),
            (3, "status"),
            (4, "status"),
            (5, "status"),
            (6, "done"),
        ]

    def test_turn_with_no_events_still_gets_done(self, live):
        live.agent.script_for = lambda sid, m: []
        rec = run_turn(live.base, "s1", "hi")
        assert rec.got_done and rec.statuses == []
        assert rec.result["response"] == "answer-to:hi"

    def test_turn_endpoint_reports_the_finished_turn(self, live):
        live.agent.script_for = lambda sid, m: [action("a"), action("b")]
        rec = run_turn(live.base, "s1", "hi")

        body = get_turn(live.base, rec.turn_id).json()

        assert body["turn_id"] == rec.turn_id
        assert body["session_id"] == "s1"
        assert body["status"] == "done"
        assert body["last_event_id"] == 2
        assert body["result"]["response"] == "answer-to:hi"
        assert body["result"]["session_id"] == "s1"

    def test_hundreds_of_events_are_all_delivered_in_order(self, live):
        steps = [action(f"a{i}") for i in range(300)]
        live.agent.script_for = lambda sid, m: steps
        rec = run_turn(live.base, "s1", "long")
        assert rec.tools == [f"a{i}" for i in range(300)]
        assert rec.got_done

    @pytest.mark.parametrize(
        "text",
        [
            "line1\nline2\n\nline4",
            "windows\r\nline",
            'quote " and \\ backslash',
            "unicode è ü 日本語 🚀",
            "ls \u2028 ps \u2029",
            "data: fake\n\nevent: done\ndata: ",  # tries to inject an SSE frame
            "x" * 100_000,
        ],
        ids=["newlines", "crlf", "quotes", "unicode", "u2028", "frame-injection", "100KB"],
    )
    def test_event_payload_survives_sse_framing(self, live, text):
        live.agent.script_for = lambda sid, m: [action(text)]
        rec = run_turn(live.base, "s1", "hi")
        assert rec.tools == [text]
        assert [n for _, n, _ in rec.sse_events] == ["status", "done"]

    def test_thoughts_are_never_streamed(self, live):
        """publish_thought is a deliberate no-op: reasoning must not leak."""
        live.agent.script_for = lambda sid, m: [
            call(lambda: events.publish_thought("s1", "secret reasoning")),
            action("tool_a"),
        ]
        rec = run_turn(live.base, "s1", "hi")
        assert rec.tools == ["tool_a"]
        assert "secret reasoning" not in "".join(d for _, _, d in rec.sse_events)

    def test_agent_receives_the_session_state_and_config(self, live):
        seen = {}
        orig = live.agent.invoke

        def spy(state, config=None):
            seen["config"] = config
            seen["user_msg"] = state.get_last_message().content
            return orig(state, config)

        live.agent.invoke = spy
        run_turn(live.base, "s-cfg", "hello there")

        assert seen["user_msg"] == "hello there"
        assert seen["config"]["configurable"]["thread_id"] == "s-cfg"
        assert seen["config"]["configurable"]["token"] == "test-token"

    def test_agent_interrupt_marker_is_stripped_from_the_result_state(self, live):
        orig = live.agent.invoke

        def invoke_with_interrupt(state, config=None):
            out = orig(state, config)
            out["__interrupt__"] = ["pending"]
            return out

        live.agent.invoke = invoke_with_interrupt
        rec = run_turn(live.base, "s1", "hi")

        assert rec.result["response"] == "answer-to:hi"
        assert rec.done_payload == {"status": "done"}

    def test_assistant_action_data_is_returned_in_the_result(self, live):
        orig = live.agent.invoke

        def invoke_with_widgets(state, config=None):
            out = orig(state, config)
            out["assistant_action_data"] = [{"type": "NAVIGATE", "payload": {"to": "x"}}]
            return out

        live.agent.invoke = invoke_with_widgets
        rec = run_turn(live.base, "s1", "hi")

        assert rec.result["assistant_action_data"] == [
            {"type": "NAVIGATE", "payload": {"to": "x"}}
        ]
        assert rec.result["agent_type"]  # active agent tier is always reported

    def test_turn_persists_the_final_state_for_the_next_turn(self, live):
        run_turn(live.base, "s1", "first")
        run_turn(live.base, "s1", "second")

        contents = [m.content for m in memory.load_state("s1").conversation.messages]

        assert contents == ["first", "answer-to:first", "second", "answer-to:second"]


# --------------------------------------------------------------------------- #
# Many calls at once
# --------------------------------------------------------------------------- #
class TestManyCalls:
    @pytest.mark.parametrize("seed", [11, 22, 33])
    def test_concurrent_sessions_each_get_own_events_done_and_answer(self, live, seed):
        rnd = random.Random(seed)
        n = 40
        scripts = {}
        for i in range(n):
            sid = f"s{i}"
            steps = []
            for k in range(rnd.randint(0, 8)):
                steps.append(action(f"{sid}:tool{k}", delay=rnd.random() * 0.03))
            if rnd.random() < 0.3:
                steps.append(sleep(rnd.random() * 0.2))  # a slow final "LLM call"
            scripts[sid] = steps
        live.agent.script_for = lambda sid, m: scripts[sid]

        with ThreadPoolExecutor(n) as ex:
            recs = list(ex.map(lambda s: run_turn(live.base, s, f"m-{s}"), scripts))

        problems = []
        for rec in recs:
            expected = [s.value for s in scripts[rec.session] if s.kind == "action"]
            if rec.error or not rec.got_done:
                problems.append(f"{rec.session}: no done ({rec.error})")
            elif rec.tools != expected:
                problems.append(f"{rec.session}: events mismatch {rec.tools}")
            elif not rec.result or rec.result["response"] != f"answer-to:m-{rec.session}":
                problems.append(f"{rec.session}: wrong/missing answer {rec.result}")
        assert not problems, f"seed={seed}\n" + "\n".join(problems)

    def test_many_sequential_turns_per_session_in_parallel(self, live):
        """20 sessions x 6 turns, sessions interleaved. Catches stale results
        (turn N answered with turn N-1), leaked events and spurious 409s."""
        n_sessions, n_turns = 20, 6
        live.agent.script_for = lambda sid, m: [
            action(f"{m}-a"),
            sleep(0.01),
            action(f"{m}-b"),
        ]

        def session(i):
            out = []
            for t in range(n_turns):
                msg = f"s{i}-turn{t}"
                out.append((msg, run_turn(live.base, f"s{i}", msg)))
            return out

        with ThreadPoolExecutor(n_sessions) as ex:
            all_turns = [x for chunk in ex.map(session, range(n_sessions)) for x in chunk]

        statuses = Counter(rec.post_status for _, rec in all_turns)
        assert statuses == {202: n_sessions * n_turns}, statuses
        assert len({rec.turn_id for _, rec in all_turns}) == n_sessions * n_turns
        for msg, rec in all_turns:
            assert rec.got_done, (msg, rec.error)
            assert rec.tools == [f"{msg}-a", f"{msg}-b"], msg
            assert rec.result["response"] == f"answer-to:{msg}", f"stale result for {msg}"

    @pytest.mark.parametrize("seed", [5, 6])
    def test_mixed_failures_never_leave_a_stream_hanging(self, live, seed):
        rnd = random.Random(seed)
        n = 40
        kinds = {
            f"s{i}": rnd.choice(
                ["ok", "exception", "system-exit", "keyboard-interrupt", "memory-error", "late-exception"]
            )
            for i in range(n)
        }

        def script(sid, msg):
            k = kinds[sid]
            if k == "ok":
                return [action(f"{sid}:0")]
            if k == "late-exception":
                return [action(f"{sid}:0"), raise_(RuntimeError("after progress"), 0.05)]
            exc = {
                "exception": RuntimeError("boom"),
                "system-exit": SystemExit(1),
                "keyboard-interrupt": KeyboardInterrupt(),
                "memory-error": MemoryError(),
            }[k]
            return [raise_(exc)]

        live.agent.script_for = script
        with ThreadPoolExecutor(n) as ex:
            recs = list(
                ex.map(
                    lambda s: run_turn(live.base, s, "m", fetch_result=False, read_timeout=15),
                    kinds,
                )
            )

        hung = [(r.session, kinds[r.session], r.error) for r in recs if not r.got_done]
        assert not hung, f"seed={seed}: streams that never got `done`: {hung}"
        # every session is usable again: no turn stayed "running"
        stuck = [s for s in kinds if live.store.active_turn(s) is not None]
        assert not stuck, f"sessions stuck with a running turn: {stuck}"
        # and the terminal status matches what happened inside the turn
        for r in recs:
            want = "done" if kinds[r.session] == "ok" else "failed"
            assert r.done_payload == {"status": want}, (r.session, kinds[r.session])


# --------------------------------------------------------------------------- #
# Errors inside a turn
# --------------------------------------------------------------------------- #
class TestErrorsInsideTurn:
    def test_exception_in_agent_sends_done_failed_and_system_error(self, live):
        live.agent.script_for = lambda sid, m: [action("x"), raise_(RuntimeError("boom"))]

        rec = run_turn(live.base, "s1", "hi")

        assert rec.got_done
        assert rec.tools == ["x"], "events published before the crash are kept"
        assert rec.done_payload == {"status": "failed"}
        assert rec.result_status == 200
        assert rec.result["response"] == "System error"
        assert rec.result["session_id"] == "s1"

    def test_polling_endpoint_reports_failed_status(self, live):
        live.agent.script_for = lambda sid, m: [raise_(RuntimeError("boom"))]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]

        body = wait_for_status(live.base, turn_id)

        assert body["status"] == "failed"
        assert body["result"]["response"] == "System error"

    def test_session_is_usable_after_a_failed_turn(self, live):
        live.agent.script_for = lambda sid, m: (
            [raise_(RuntimeError("boom"))] if m == "bad" else [action("fine")]
        )
        assert run_turn(live.base, "s1", "bad", fetch_result=False).got_done

        rec = run_turn(live.base, "s1", "good")

        assert rec.post_status == 202, "session must not stay 409 after a failure"
        assert rec.result["response"] == "answer-to:good"

    def test_failed_turn_does_not_remember_a_half_finished_state(self, live, monkeypatch):
        remembered = []
        monkeypatch.setattr(live.routes, "remember_state", remembered.append)
        live.agent.script_for = lambda sid, m: [raise_(RuntimeError("boom"))]

        run_turn(live.base, "s1", "hi")

        assert remembered == []

    def test_agent_that_returns_without_an_assistant_message_is_a_failed_turn(self, live):
        """No answer was produced -> status `failed`, but the (partial) state is
        still published so the conversation history is not lost."""
        orig = live.agent.invoke

        def no_answer(state, config=None):
            orig(state, config)
            state.conversation.messages.pop()  # drop the assistant message again
            return dict(state.__dict__)

        live.agent.invoke = no_answer
        rec = run_turn(live.base, "s1", "hi")

        assert rec.done_payload == {"status": "failed"}
        assert rec.result["response"] == "System error"
        assert memory.load_state("s1").get_last_message().role == "user"

    def test_remember_state_failure_marks_turn_failed_and_releases_session(
        self, live, monkeypatch
    ):
        real_remember = live.routes.remember_state

        def exploding(state):
            raise RuntimeError("memory store exploded")

        monkeypatch.setattr(live.routes, "remember_state", exploding)

        rec = run_turn(live.base, "s1", "hi")

        assert rec.done_payload == {"status": "failed"}
        assert rec.result["response"] == "System error"
        assert live.store.active_turn("s1") is None
        monkeypatch.setattr(live.routes, "remember_state", real_remember)  # recovers
        assert post_turn(live.base, "s1", "again", seed=False).status_code == 202

    def test_persist_state_failure_does_not_swallow_the_answer(self, live, monkeypatch):
        def failing_persist(state):
            raise OSError("disk full")

        monkeypatch.setattr(live.routes, "persist_state", failing_persist)

        rec = run_turn(live.base, "s1", "hi")

        assert rec.done_payload == {"status": "done"}
        assert rec.result["response"] == "answer-to:hi"
        # the in-memory state is what the next turn loads: it must be current
        assert memory.load_state("s1").get_last_message().content == "answer-to:hi"

    def test_save_state_failure_while_preparing_the_turn_releases_it(self, live, monkeypatch):
        """A failure while PREPARING the turn (before the agent starts) must not
        leave the session stuck on a running turn -> permanent 409."""
        seed_session("s1")
        calls = {"n": 0}
        real = live.routes.save_state

        def flaky_save(state):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("disk full")
            return real(state)

        monkeypatch.setattr(live.routes, "save_state", flaky_save)

        # separate connections: uvicorn closes the one that saw the 500
        first = post_turn(live.base, "s1", "a", seed=False)
        second = post_turn(live.base, "s1", "b", seed=False)

        assert first.status_code == 500
        assert second.status_code == 202, "turn from the failed POST must be released"
        assert len(live.agent.invocations) == 1, "the failed POST must not run the agent"

    def test_executor_refusing_the_job_marks_the_turn_failed(self, live, monkeypatch):
        from concurrent.futures import ThreadPoolExecutor as TPE

        dead_pool = TPE(max_workers=1)
        dead_pool.shutdown()
        monkeypatch.setattr(live.routes, "_TURN_POOL", dead_pool)
        seed_session("s1")

        with httpx.Client(base_url=live.base, timeout=10) as c:
            try:
                c.post("/agent", data={"message": "a", "session_id": "s1"}, headers=AUTH)
            except httpx.HTTPError:
                pass  # the server may drop the connection after the background error

        deadline = time.time() + 5
        while live.store.active_turn("s1") is not None and time.time() < deadline:
            time.sleep(0.02)
        assert live.store.active_turn("s1") is None, "turn must never stay `running`"
        assert live.store.get(live.store.latest_turn("s1"))["status"] == "failed"


# --------------------------------------------------------------------------- #
# Stuck turns and the watchdog
# --------------------------------------------------------------------------- #
class TestWatchdog:
    def test_hung_turn_gets_done_timeout_when_the_watchdog_fires(self, live):
        live.routes.AGENT_TURN_TIMEOUT = 0.6
        live.agent.script_for = lambda sid, m: [action("start"), hang(3.0)]

        rec = run_turn(live.base, "s1", "stuck")

        assert rec.got_done
        assert rec.t_done - rec.t_post < 1.8, "done must arrive ~AGENT_TURN_TIMEOUT after the POST"
        assert rec.tools == ["start"]
        assert rec.done_payload == {"status": "timeout"}
        assert "too long" in rec.result["response"]
        assert rec.result["agent_type"], "timeout result carries the active agent tier"
        assert live.store.active_turn("s1") is None

    def test_session_accepts_a_new_turn_right_after_a_timeout(self, live):
        live.routes.AGENT_TURN_TIMEOUT = 0.4
        live.agent.script_for = lambda sid, m: [hang(1.0)] if m == "stuck" else []
        run_turn(live.base, "s1", "stuck", fetch_result=False)

        r = post_turn(live.base, "s1", "next")

        assert r.status_code == 202

    def test_late_completion_of_a_timed_out_turn_changes_nothing(self, live, monkeypatch):
        remembered, persisted = [], []
        monkeypatch.setattr(live.routes, "remember_state", remembered.append)
        monkeypatch.setattr(live.routes, "persist_state", persisted.append)
        live.routes.AGENT_TURN_TIMEOUT = 0.4
        live.agent.script_for = lambda sid, m: [hang(1.0)]

        rec = run_turn(live.base, "s1", "stuck", fetch_result=False)
        assert rec.got_done
        time.sleep(1.4)  # let the hung thread finish

        snap = live.store.get(rec.turn_id)
        assert snap["status"] == "timeout"
        assert "too long" in snap["result"]["response"], "timeout result was overwritten"
        assert remembered == [] and persisted == [], "a lost race must not save state"
        # and the stream still shows exactly one terminal frame
        frames = read_stream(live.base, rec.turn_id)
        assert [n for _, n, _ in frames].count("done") == 1

    def test_events_of_a_timed_out_turn_do_not_leak_into_the_next_turn(self, live):
        """The watchdog cannot kill the hung thread. Because events are bound to
        a turn (turn_context), its late events are dropped instead of showing up
        in the NEXT turn's stream."""
        live.routes.AGENT_TURN_TIMEOUT = 0.4

        def script(sid, msg):
            if msg == "old":
                return [action("old-1"), hang(1.5), action("OLD-ZOMBIE")]
            return [action("new-1"), sleep(2.5), action("new-2")]

        live.agent.script_for = script
        run_turn(live.base, "s1", "old", fetch_result=False)
        live.routes.AGENT_TURN_TIMEOUT = 30  # the new turn gets a normal budget

        rec = run_turn(live.base, "s1", "new", read_timeout=15)

        assert rec.post_status == 202
        assert rec.tools == ["new-1", "new-2"]
        assert rec.done_payload == {"status": "done"}

    def test_turns_waiting_in_the_agent_pool_still_honour_the_timeout(self, live, monkeypatch):
        from concurrent.futures import ThreadPoolExecutor as TPE

        pool = TPE(max_workers=2)
        release_workers = threading.Event()
        for _ in range(2):
            pool.submit(release_workers.wait)
        monkeypatch.setattr(live.routes, "_TURN_POOL", pool)
        live.routes.AGENT_TURN_TIMEOUT = 1.0
        live.agent.script_for = lambda sid, m: [action("x")]
        threading.Timer(1.6, release_workers.set).start()

        try:
            with ThreadPoolExecutor(6) as ex:
                recs = list(
                    ex.map(lambda i: run_turn(live.base, f"s{i}", "m", fetch_result=False), range(6))
                )
        finally:
            release_workers.set()
            pool.shutdown(wait=True)

        assert all(rec.got_done for rec in recs), [rec.error for rec in recs]
        assert {rec.done_payload["status"] for rec in recs} == {"timeout"}
        worst = max(r.t_done - r.t_post for r in recs)
        assert worst < live.routes.AGENT_TURN_TIMEOUT + 0.5, (
            f"slowest queued turn needed {worst:.1f}s from POST to done "
            f"(timeout is {live.routes.AGENT_TURN_TIMEOUT}s)"
        )


# --------------------------------------------------------------------------- #
# Reconnects, late connections, several readers
# --------------------------------------------------------------------------- #
def _open_stream(base, turn_id, headers=None, params=None):
    c = httpx.Client(base_url=base, timeout=20)
    cm = c.stream(
        "GET",
        f"/agent/turns/{turn_id}/events",
        headers=AUTH if headers is None else headers,
        params=params,
    )
    resp = cm.__enter__()
    return c, cm, resp


class TestReconnectAndRetry:
    def test_connecting_after_the_turn_finished_replays_events_then_done(self, live):
        live.agent.script_for = lambda sid, m: [action("x"), action("y")]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        wait_for_status(live.base, turn_id)

        t0 = time.monotonic()
        frames = read_stream(live.base, turn_id)

        assert [n for _, n, _ in frames] == ["status", "status", "done"]
        assert time.monotonic() - t0 < 1.0

    def test_turn_endpoint_is_idempotent_for_retries(self, live):
        live.agent.script_for = lambda sid, m: [action("x")]
        rec = run_turn(live.base, "s1", "hi")
        with httpx.Client(base_url=live.base, timeout=10) as c:
            bodies = [c.get(f"/agent/turns/{rec.turn_id}", headers=AUTH) for _ in range(5)]
        assert {b.status_code for b in bodies} == {200}
        assert len({b.text for b in bodies}) == 1

    def test_turn_endpoint_reports_running_with_no_result_yet(self, live):
        live.agent.script_for = lambda sid, m: [action("started"), sleep(0.8)]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        time.sleep(0.2)

        r = get_turn(live.base, turn_id)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "running"
        assert body["result"] is None
        assert body["last_event_id"] == 1

    def test_dropped_stream_then_reconnect_with_last_event_id_gets_only_the_rest(self, live):
        live.agent.script_for = lambda sid, m: [
            action("t1"), sleep(0.4), action("t2"), sleep(0.4), action("t3"), sleep(0.3)
        ]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        c1, cm1, r1 = _open_stream(live.base, turn_id)
        first = next(parse_sse_frames(sse_lines(r1)))
        assert first[:2] == (1, "status")
        cm1.__exit__(None, None, None)  # connection dies mid-turn
        c1.close()

        frames = read_stream(live.base, turn_id, headers={**AUTH, "Last-Event-ID": "1"})

        assert [(i, n) for i, n, _ in frames][:2] == [(2, "status"), (3, "status")]
        assert frames[-1][1] == "done"
        assert [d for _, n, d in frames if n == "status"] == [
            '{"type": "action", "tool": "t2"}',
            '{"type": "action", "tool": "t3"}',
        ]
        assert get_turn(live.base, turn_id).json()["result"]["response"] == "answer-to:hi"

    def test_last_event_id_query_param_works_like_the_header(self, live):
        live.agent.script_for = lambda sid, m: [action("a"), action("b"), action("c")]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        wait_for_status(live.base, turn_id)

        frames = read_stream(live.base, turn_id, params={"last_event_id": "2"})

        assert [(i, n) for i, n, _ in frames] == [(3, "status"), (4, "done")]

    def test_header_wins_over_query_param(self, live):
        live.agent.script_for = lambda sid, m: [action("a"), action("b"), action("c")]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        wait_for_status(live.base, turn_id)

        frames = read_stream(
            live.base,
            turn_id,
            headers={**AUTH, "Last-Event-ID": "3"},
            params={"last_event_id": "0"},
        )

        assert [(i, n) for i, n, _ in frames] == [(4, "done")]

    @pytest.mark.parametrize("garbage", ["abc", "-5", "1.5"])
    def test_garbage_last_event_id_replays_from_the_start(self, live, garbage):
        live.agent.script_for = lambda sid, m: [action("a"), action("b")]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        wait_for_status(live.base, turn_id)

        frames = read_stream(live.base, turn_id, params={"last_event_id": garbage})

        assert [n for _, n, _ in frames] == ["status", "status", "done"]

    def test_last_event_id_past_the_end_only_gets_done(self, live):
        live.agent.script_for = lambda sid, m: [action("a")]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        wait_for_status(live.base, turn_id)

        frames = read_stream(live.base, turn_id, headers={**AUTH, "Last-Event-ID": "99"})

        assert [n for _, n, _ in frames] == ["done"]

    def test_repeated_drops_and_reconnects_see_every_event_exactly_once(self, live):
        total = 10
        live.agent.script_for = lambda sid, m: [
            action(f"t{i}", delay=0.1) for i in range(total)
        ]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        seen_ids: list[int] = []
        got_done = False
        for _ in range(60):
            c, cm, r = _open_stream(
                live.base,
                turn_id,
                headers={**AUTH, "Last-Event-ID": str(seen_ids[-1] if seen_ids else 0)},
            )
            try:
                for event_id, name, _ in parse_sse_frames(sse_lines(r)):
                    if name == "done":
                        got_done = True
                    else:
                        seen_ids.append(event_id)
                    break  # drop the connection after ONE frame, then reconnect
            finally:
                cm.__exit__(None, None, None)
                c.close()
            if got_done:
                break
        assert got_done, "never saw done across the reconnects"
        assert seen_ids == list(range(1, total + 1)), "events lost or duplicated"

    def test_two_streams_on_the_same_turn_both_get_every_event(self, live):
        """Events are never consumed: readers cannot steal events from each other."""
        live.agent.script_for = lambda sid, m: [action(f"t{i}", delay=0.1) for i in range(6)]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        results = []

        def reader():
            c, cm, r = _open_stream(live.base, turn_id)
            try:
                results.append([(i, n) for i, n, _ in parse_sse_frames(sse_lines(r))])
            finally:
                cm.__exit__(None, None, None)
                c.close()

        ts = [threading.Thread(target=reader) for _ in range(3)]
        [t.start() for t in ts]
        [t.join(timeout=15) for t in ts]

        expected = [(i, "status") for i in range(1, 7)] + [(7, "done")]
        assert results == [expected] * 3, results

    def test_stream_for_unknown_turn_is_404_not_a_hang(self, live):
        with httpx.Client(base_url=live.base, timeout=5) as c:
            assert c.get("/agent/turns/nope/events", headers=AUTH).status_code == 404

    def test_stream_requires_auth(self, live):
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        with httpx.Client(base_url=live.base, timeout=5) as c:
            assert c.get(f"/agent/turns/{turn_id}/events").status_code == 401

    def test_stream_accepts_token_query_param_for_eventsource(self, live):
        live.agent.script_for = lambda sid, m: [action("x")]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        with httpx.Client(base_url=live.base, timeout=10) as c:
            with c.stream("GET", f"/agent/turns/{turn_id}/events", params={"token": "abc"}) as r:
                assert r.status_code == 200
                frames = list(parse_sse_frames(sse_lines(r)))
        assert frames[-1][1] == "done"
        assert "abc" in live.auth_calls, "the query token must be what gets validated"

    def test_stream_of_someone_elses_turn_is_404(self, live):
        live.users["mallory-token"] = "user-2"
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        with httpx.Client(base_url=live.base, timeout=5) as c:
            r = c.get(f"/agent/turns/{turn_id}/events", headers=auth_for("mallory-token"))
        assert r.status_code == 404

    def test_streaming_response_headers_disable_buffering(self, live):
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        with httpx.Client(base_url=live.base, timeout=10) as c:
            with c.stream("GET", f"/agent/turns/{turn_id}/events", headers=AUTH) as r:
                list(r.iter_text())
                headers = r.headers
        assert headers["content-type"].startswith("text/event-stream")
        assert "no-cache" in headers["cache-control"]
        assert headers["x-accel-buffering"] == "no"

    def test_keepalive_comments_are_sent_during_a_long_silence(self, live, monkeypatch):
        """Idle proxies kill silent connections; the stream must emit comments."""
        real_iter_sse = events.iter_sse

        def fast_iter(turn_id, after=0):
            return real_iter_sse(turn_id, after, poll_interval=0.01, keepalive_every=0.05)

        monkeypatch.setattr(live.routes, "iter_sse", fast_iter)
        live.agent.script_for = lambda sid, m: [sleep(0.6)]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]

        with httpx.Client(base_url=live.base, timeout=10) as c:
            with c.stream("GET", f"/agent/turns/{turn_id}/events", headers=AUTH) as r:
                raw = list(sse_lines(r))

        assert any(line.startswith(": keep-alive") for line in raw), raw
        assert raw[0] == "retry: 2000"

    def test_streams_are_scoped_to_their_own_turn(self, live):
        """Turn 1's stream, opened while turn 2 is running, still ends with turn
        1's own events + done (the old session-keyed stream could not tell)."""
        live.agent.script_for = lambda sid, m: (
            [action("first")] if m == "first" else [action("second"), sleep(1.0)]
        )
        first = run_turn(live.base, "s1", "first")
        second_id = post_turn(live.base, "s1", "second").json()["turn_id"]
        time.sleep(0.15)

        t0 = time.monotonic()
        frames = read_stream(live.base, first.turn_id)

        assert time.monotonic() - t0 < 0.8, "turn 1's stream must not wait for turn 2"
        assert [n for _, n, _ in frames] == ["status", "done"]
        assert '"first"' in frames[0][2]
        assert get_turn(live.base, second_id).json()["status"] in ("running", "done")

    def test_stream_opened_before_agent_produces_events_gets_them_live(self, live):
        live.agent.script_for = lambda sid, m: [
            sleep(0.3), action("late-1"), sleep(0.2), action("late-2")
        ]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]

        frames = read_stream(live.base, turn_id)

        assert [n for _, n, _ in frames] == ["status", "status", "done"]


# --------------------------------------------------------------------------- #
# Concurrency rules of the endpoint
# --------------------------------------------------------------------------- #
class TestInFlightRules:
    def test_second_message_while_turn_runs_is_rejected_with_409(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.8)]
        first = post_turn(live.base, "s1", "a")
        assert first.status_code == 202

        second = post_turn(live.base, "s1", "b")

        assert second.status_code == 409
        detail = second.json()["detail"]
        assert detail["active_turn_id"] == first.json()["turn_id"]
        assert "still being processed" in detail["message"]

    def test_rejected_message_is_not_added_to_the_conversation(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.5)]
        post_turn(live.base, "s1", "a")
        post_turn(live.base, "s1", "rejected")
        time.sleep(0.8)

        contents = [m.content for m in memory.load_state("s1").conversation.messages]

        assert "rejected" not in contents

    def test_other_sessions_are_not_blocked_by_a_running_turn(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.6)]
        assert post_turn(live.base, "s1", "a").status_code == 202
        assert post_turn(live.base, "s2", "a").status_code == 202

    def test_burst_of_simultaneous_posts_accepts_exactly_one(self, live):
        seed_session("s1")
        live.agent.script_for = lambda sid, m: [sleep(0.8)]
        with ThreadPoolExecutor(12) as ex:
            codes = list(
                ex.map(lambda i: post_turn(live.base, "s1", f"m{i}", seed=False).status_code, range(12))
            )
        assert Counter(codes) == {202: 1, 409: 11}, Counter(codes)
        assert len(live.agent.invocations) == 1

    def test_follow_up_sent_the_instant_done_is_seen_is_never_rejected(self, live):
        """finish() releases the session in the same critical section that makes
        the turn terminal: a frontend that reacts to `done` immediately must
        not hit a 409."""
        live.agent.script_for = lambda sid, m: [action("x")]

        def chatter(i):
            return [
                run_turn(live.base, f"s{i}", f"m{k}", fetch_result=False).post_status
                for k in range(10)
            ]

        with ThreadPoolExecutor(20) as ex:
            codes = Counter(c for chunk in ex.map(chatter, range(20)) for c in chunk)
        assert codes == {202: 20 * 10}, codes

    # ---- Idempotency-Key ---------------------------------------------------
    def test_retried_post_with_same_idempotency_key_returns_the_same_turn(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.5)]
        headers = {**AUTH, "Idempotency-Key": "req-1"}

        first = post_turn(live.base, "s1", "hi", headers=headers)
        retry = post_turn(live.base, "s1", "hi", headers=headers)

        assert first.status_code == retry.status_code == 202
        assert retry.json() == first.json()
        time.sleep(0.8)
        assert len(live.agent.invocations) == 1, "a retry must not run the agent twice"

    def test_idempotent_retry_does_not_duplicate_the_user_message(self, live):
        live.agent.script_for = lambda sid, m: []
        headers = {**AUTH, "Idempotency-Key": "req-1"}
        first = post_turn(live.base, "s1", "hi", headers=headers)
        wait_for_status(live.base, first.json()["turn_id"])

        post_turn(live.base, "s1", "hi", headers=headers)

        users = [m for m in memory.load_state("s1").conversation.messages if m.role == "user"]
        assert len(users) == 1

    def test_idempotent_retry_after_the_turn_finished_still_returns_that_turn(self, live):
        live.agent.script_for = lambda sid, m: [action("x")]
        headers = {**AUTH, "Idempotency-Key": "req-1"}
        first = post_turn(live.base, "s1", "hi", headers=headers).json()
        wait_for_status(live.base, first["turn_id"])

        retry = post_turn(live.base, "s1", "hi", headers=headers)

        assert retry.status_code == 202 and retry.json() == first
        assert len(live.agent.invocations) == 1

    def test_different_idempotency_key_while_running_is_a_409(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.6)]
        post_turn(live.base, "s1", "a", headers={**AUTH, "Idempotency-Key": "k1"})

        r = post_turn(live.base, "s1", "b", headers={**AUTH, "Idempotency-Key": "k2"})

        assert r.status_code == 409

    def test_same_idempotency_key_in_different_sessions_is_independent(self, live):
        live.agent.script_for = lambda sid, m: []
        headers = {**AUTH, "Idempotency-Key": "shared"}

        a = post_turn(live.base, "s1", "hi", headers=headers).json()
        b = post_turn(live.base, "s2", "hi", headers=headers).json()

        assert a["turn_id"] != b["turn_id"]

    def test_new_idempotency_key_after_finish_starts_a_new_turn(self, live):
        live.agent.script_for = lambda sid, m: []
        a = post_turn(live.base, "s1", "one", headers={**AUTH, "Idempotency-Key": "k1"}).json()
        wait_for_status(live.base, a["turn_id"])

        b = post_turn(live.base, "s1", "two", headers={**AUTH, "Idempotency-Key": "k2"}).json()

        assert a["turn_id"] != b["turn_id"]

    # ---- reset -------------------------------------------------------------
    def test_reset_during_a_running_turn_is_not_undone_by_the_turn_finishing(self, live):
        """/agent/reset clears the session AND its turns, so the zombie thread's
        finish() loses and neither remembers nor persists anything."""
        live.agent.script_for = lambda sid, m: [action("x"), sleep(0.8)]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        time.sleep(0.2)
        with httpx.Client(base_url=live.base, timeout=10) as c:
            assert c.post("/agent/reset", data={"session_id": "s1"}, headers=AUTH).status_code == 200
        assert memory.load_state("s1") is None

        time.sleep(1.2)  # the turn thread finishes now

        assert memory.load_state("s1") is None, "session came back after reset"
        assert live.store.get(turn_id) is None, "turn came back after reset"
        assert live.store.active_turn("s1") is None

    def test_reset_while_streaming_ends_the_stream_with_gone(self, live):
        live.agent.script_for = lambda sid, m: [sleep(2.0)]
        turn_id = post_turn(live.base, "s1", "hi").json()["turn_id"]
        c, cm, r = _open_stream(live.base, turn_id)
        try:
            time.sleep(0.3)
            with httpx.Client(base_url=live.base, timeout=10) as c2:
                c2.post("/agent/reset", data={"session_id": "s1"}, headers=AUTH)
            frames = list(parse_sse_frames(sse_lines(r)))
        finally:
            cm.__exit__(None, None, None)
            c.close()
        assert frames[-1][1] == "done"
        assert frames[-1][2] == '{"status": "gone"}'

    def test_session_can_be_re_initialised_after_reset(self, live):
        with httpx.Client(base_url=live.base, timeout=10) as c:
            sid = c.post("/agent/init", headers=AUTH).json()["session_id"]
            c.post("/agent/reset", data={"session_id": sid}, headers=AUTH)
            fresh = c.post("/agent/init", headers=AUTH)
            gone = c.post("/agent", data={"message": "hi", "session_id": sid}, headers=AUTH)

        assert fresh.status_code == 201
        assert fresh.json()["session_id"] != sid
        assert gone.status_code == 404


# --------------------------------------------------------------------------- #
# Full flow through /agent/init, the way the frontend uses it
# --------------------------------------------------------------------------- #
class TestFullFlow:
    def test_init_post_stream_poll_second_turn(self, live):
        live.agent.script_for = lambda sid, m: [action(f"tool-for-{m}")]
        with httpx.Client(base_url=live.base, timeout=10) as c:
            init = c.post("/agent/init", headers=AUTH)
            assert init.status_code == 201
            sid = init.json()["session_id"]

            for msg in ("first", "second"):
                r = c.post("/agent", data={"message": msg, "session_id": sid}, headers=AUTH)
                assert r.status_code == 202
                turn_id = r.json()["turn_id"]
                frames = read_stream(live.base, turn_id)
                assert [n for _, n, _ in frames] == ["status", "done"]
                assert f"tool-for-{msg}" in frames[0][2]
                body = c.get(f"/agent/turns/{turn_id}", headers=AUTH).json()
                assert body["result"]["response"] == f"answer-to:{msg}"

            session = c.get(f"/agent/session/{sid}", headers=AUTH).json()
            assert session["active_turn_id"] is None
            assert session["latest_turn_id"] == turn_id

    def test_page_reload_can_resume_a_running_turn_through_the_session_endpoint(self, live):
        live.agent.script_for = lambda sid, m: [action("a"), sleep(0.6), action("b")]
        with httpx.Client(base_url=live.base, timeout=10) as c:
            sid = c.post("/agent/init", headers=AUTH).json()["session_id"]
            turn_id = c.post(
                "/agent", data={"message": "hi", "session_id": sid}, headers=AUTH
            ).json()["turn_id"]
            time.sleep(0.2)

            # "reload": the only thing the frontend still knows is the session id
            resumed = c.get(f"/agent/session/{sid}", headers=AUTH).json()
            assert resumed["active_turn_id"] == turn_id

        frames = read_stream(live.base, resumed["active_turn_id"])
        assert [n for _, n, _ in frames] == ["status", "status", "done"]
