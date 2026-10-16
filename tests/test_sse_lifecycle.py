"""
End-to-end SSE contract tests (real uvicorn + real routes/events/memory).

The contract the frontend relies on, for EVERY turn, whatever happens inside it:

    POST /agent  -> 202
    GET  /agent/stream/{sid}   -> zero or more `status` events, then exactly
                                  one `done`, then the stream closes
    GET  /agent/result/{sid}   -> 200 with the answer of THIS turn

Tests marked xfail(strict=True) document confirmed bugs. They are written as
the *desired* behaviour, so the day you fix the bug they start passing, pytest
reports XPASS(strict) as a failure, and you just delete the marker.
"""

from __future__ import annotations

import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

import sse_harness as h
from sse_harness import (
    AUTH,
    action,
    call,
    hang,
    parse_sse_lines,
    sse_lines,
    raise_,
    run_turn,
    sleep,
    thought,
)
from app.agent import events, memory


def thoughts_of(rec):
    return [s["content"] for s in rec.statuses if s["type"] == "thought"]


def tools_of(rec):
    return [s["tool"] for s in rec.statuses if s["type"] == "action"]


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
        assert (
            live.routes.load_state(rec.session).force_role == expected_role
        )

    def test_force_role_rejects_unknown_values(self, live):
        rec = run_turn(
            live.base,
            "force-role-invalid",
            "hello",
            extra_form={"force_role": "unknown"},
        )

        assert rec.post_status == 422

    def test_status_events_in_order_then_exactly_one_done(self, live):
        live.agent.script_for = lambda sid, m: [
            thought("plan"),
            action("tool_a"),
            thought("observe"),
            action("tool_b"),
            thought("conclude"),
        ]
        rec = run_turn(live.base, "s1", "hello")
        assert rec.error is None
        assert [(s["type"], s.get("content") or s.get("tool")) for s in rec.statuses] == [
            ("thought", "plan"),
            ("action", "tool_a"),
            ("thought", "observe"),
            ("action", "tool_b"),
            ("thought", "conclude"),
        ]
        assert [n for _, n, _ in rec.sse_events].count("done") == 1
        assert rec.sse_events[-1][1] == "done"
        assert rec.result["response"] == "answer-to:hello"

    def test_turn_with_no_reasoning_steps_still_gets_done(self, live):
        live.agent.script_for = lambda sid, m: []
        rec = run_turn(live.base, "s1", "hi")
        assert rec.got_done and rec.statuses == []
        assert rec.result["response"] == "answer-to:hi"

    def test_hundreds_of_reasoning_steps_are_all_delivered_in_order(self, live):
        steps = []
        for i in range(150):
            steps += [thought(f"t{i}"), action(f"a{i}")]
        live.agent.script_for = lambda sid, m: steps
        rec = run_turn(live.base, "s1", "long")
        assert thoughts_of(rec) == [f"t{i}" for i in range(150)]
        assert tools_of(rec) == [f"a{i}" for i in range(150)]
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
    def test_thought_text_survives_sse_framing(self, live, text):
        live.agent.script_for = lambda sid, m: [thought(text)]
        rec = run_turn(live.base, "s1", "hi")
        assert thoughts_of(rec) == [text]
        assert [n for _, n, _ in rec.sse_events] == ["status", "done"]


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
                steps.append(thought(f"{sid}:{k}", delay=rnd.random() * 0.03))
                if rnd.random() < 0.6:
                    steps.append(action(f"{sid}:tool{k}", delay=rnd.random() * 0.03))
            if rnd.random() < 0.3:
                steps.append(sleep(rnd.random() * 0.2))  # a slow final "LLM call"
            scripts[sid] = steps
        live.agent.script_for = lambda sid, m: scripts[sid]

        with ThreadPoolExecutor(n) as ex:
            recs = list(ex.map(lambda s: run_turn(live.base, s, f"m-{s}"), scripts))

        problems = []
        for rec in recs:
            exp_thoughts = [s.value for s in scripts[rec.session] if s.kind == "thought"]
            exp_tools = [s.value for s in scripts[rec.session] if s.kind == "action"]
            if rec.error or not rec.got_done:
                problems.append(f"{rec.session}: no done ({rec.error})")
            elif thoughts_of(rec) != exp_thoughts or tools_of(rec) != exp_tools:
                problems.append(f"{rec.session}: events mismatch {thoughts_of(rec)}")
            elif not rec.result or rec.result["response"] != f"answer-to:m-{rec.session}":
                problems.append(f"{rec.session}: wrong/missing answer {rec.result}")
        assert not problems, f"seed={seed}\n" + "\n".join(problems)

    def test_many_sequential_turns_per_session_in_parallel(self, live):
        """20 sessions x 6 turns, sessions interleaved. Catches stale `__done__`,
        stale results (turn N answered with turn N-1) and spurious 409s."""
        n_sessions, n_turns = 20, 6
        live.agent.script_for = lambda sid, m: [
            thought(f"{m}-a", delay=0.01),
            action("tool"),
            thought(f"{m}-b", delay=0.01),
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
        for msg, rec in all_turns:
            assert rec.got_done, (msg, rec.error)
            assert thoughts_of(rec) == [f"{msg}-a", f"{msg}-b"], msg
            assert rec.result["response"] == f"answer-to:{msg}", f"stale result for {msg}"

    @pytest.mark.parametrize("seed", [5, 6])
    def test_mixed_failures_never_leave_a_stream_hanging(self, live, seed):
        rnd = random.Random(seed)
        n = 40
        kinds = {}
        for i in range(n):
            kinds[f"s{i}"] = rnd.choice(
                ["ok", "exception", "system-exit", "keyboard-interrupt", "memory-error", "late-exception"]
            )

        def script(sid, msg):
            k = kinds[sid]
            if k == "ok":
                return [thought(f"{sid}:0")]
            if k == "late-exception":
                return [thought(f"{sid}:0"), action("t"), raise_(RuntimeError("after progress"), 0.05)]
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
        # and the sessions are all usable again (in-flight flag released)
        assert not memory._IN_FLIGHT, f"sessions stuck in flight: {memory._IN_FLIGHT}"


# --------------------------------------------------------------------------- #
# Errors inside a turn
# --------------------------------------------------------------------------- #
class TestErrorsInsideTurn:
    def test_exception_in_agent_sends_done_and_system_error(self, live):
        live.agent.script_for = lambda sid, m: [thought("x"), raise_(RuntimeError("boom"))]
        rec = run_turn(live.base, "s1", "hi", fetch_result=False)
        assert rec.got_done
        assert thoughts_of(rec) == ["x"]
        assert events.get_result("s1")["response"] == "System error"

    def test_session_is_usable_after_a_failed_turn(self, live):
        live.agent.script_for = lambda sid, m: (
            [raise_(RuntimeError("boom"))] if m == "bad" else [thought("fine")]
        )
        assert run_turn(live.base, "s1", "bad", fetch_result=False).got_done
        rec = run_turn(live.base, "s1", "good")
        assert rec.post_status == 202, "session must not stay 409 after a failure"
        assert rec.result["response"] == "answer-to:good"

    def test_save_state_failure_does_not_swallow_the_answer(self, live, monkeypatch):
        def failing_save(state):
            if getattr(failing_save, "armed", False):
                raise OSError("disk full")
            memory._STATE_STORE[state.session_id] = state

        monkeypatch.setattr(live.routes, "save_state", failing_save)
        failing_save.armed = False
        live.agent.script_for = lambda sid, m: [thought("x")]

        # first save (in POST /agent) works; the one after the turn fails
        orig_invoke = live.agent.invoke

        def invoke_then_arm(state, config=None):
            failing_save.armed = True
            return orig_invoke(state, config)

        live.agent.invoke = invoke_then_arm
        rec = run_turn(live.base, "s1", "hi")
        assert rec.got_done
        assert rec.result["response"] == "answer-to:hi"

    def test_publish_done_failure_still_releases_the_session(self, live, monkeypatch):
        real_publish_done = live.routes.publish_done
        calls = {"n": 0}

        def flaky(key, result):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("queue exploded")
            return real_publish_done(key, result)

        monkeypatch.setattr(live.routes, "publish_done", flaky)
        live.agent.script_for = lambda sid, m: [thought("x")]
        with httpx.Client(base_url=live.base, timeout=10) as c:
            assert c.post("/agent", data={"message": "a", "session_id": "s1"}, headers=AUTH).status_code == 202
            deadline = time.time() + 5
            while memory.is_in_flight("s1") and time.time() < deadline:
                time.sleep(0.05)
            assert not memory.is_in_flight("s1"), "in-flight flag leaked -> permanent 409"
            assert c.post("/agent", data={"message": "b", "session_id": "s1"}, headers=AUTH).status_code == 202

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: the fallback results built in _run_agent ('System error' and the "
            "watchdog timeout message) have no `agent_type`, but AgentResponse "
            "requires it. GET /agent/result raises ValidationError -> HTTP 500. The "
            "stream says `done`, then the frontend can never fetch the message."
        ),
    )
    def test_result_endpoint_works_after_a_crashed_turn(self, live):
        live.agent.script_for = lambda sid, m: [raise_(RuntimeError("boom"))]
        rec = run_turn(live.base, "s1", "hi")
        assert rec.result_status == 200, f"/agent/result -> {rec.result_status}"
        assert rec.result["response"] == "System error"


# --------------------------------------------------------------------------- #
# Stuck turns and the watchdog
# --------------------------------------------------------------------------- #
class TestWatchdog:
    def test_hung_turn_gets_done_when_the_watchdog_fires(self, live):
        live.routes.AGENT_TURN_TIMEOUT = 0.6
        live.agent.script_for = lambda sid, m: [thought("start"), hang(3.0)]
        rec = run_turn(live.base, "s1", "stuck", fetch_result=False)
        assert rec.got_done
        assert rec.t_done - rec.t_post < 1.8, "done must arrive ~AGENT_TURN_TIMEOUT after the POST"
        assert "too long" in events.get_result("s1")["response"]
        assert not memory.is_in_flight("s1")

    def test_late_completion_of_a_timed_out_turn_does_not_publish_a_second_done(self, live):
        live.routes.AGENT_TURN_TIMEOUT = 0.4
        live.agent.script_for = lambda sid, m: [hang(1.0)]
        rec = run_turn(live.base, "s1", "stuck", fetch_result=False)
        assert rec.got_done
        time.sleep(1.4)  # let the hung thread finish
        assert "too long" in events.get_result("s1")["response"], "timeout result was overwritten"
        leftovers = []
        q = events.get_queue("s1")
        while not q.empty():
            leftovers.append(q.get_nowait())
        assert "__done__" not in leftovers[1:], leftovers  # only the first (watchdog) one

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: the watchdog cannot stop the hung thread. It clears in-flight and "
            "publishes `done`, so the user can send a new message while the OLD thread "
            "is still running on the SAME AgentState object. When it wakes up it keeps "
            "publishing thoughts/actions into the NEW turn's stream (and save_state()s "
            "its stale state over the new one). Turn-scope the events (turn id) and "
            "drop events/saves from a superseded turn."
        ),
    )
    def test_events_of_a_timed_out_turn_do_not_leak_into_the_next_turn(self, live):
        live.routes.AGENT_TURN_TIMEOUT = 0.4

        def script(sid, msg):
            if msg == "old":
                return [thought("old-1"), hang(1.5), thought("OLD-ZOMBIE"), action("old_tool")]
            return [thought("new-1"), sleep(2.5), thought("new-2")]

        live.agent.script_for = script
        run_turn(live.base, "s1", "old", fetch_result=False)
        live.routes.AGENT_TURN_TIMEOUT = 30  # the new turn gets a normal budget
        rec = run_turn(live.base, "s1", "new", read_timeout=15, fetch_result=False)
        assert rec.post_status == 202
        assert thoughts_of(rec) == ["new-1", "new-2"]
        assert tools_of(rec) == []

    def test_turns_waiting_in_the_agent_pool_still_honour_the_timeout(
        self, live, monkeypatch
    ):
        from concurrent.futures import ThreadPoolExecutor as TPE

        pool = TPE(max_workers=2)
        release_workers = threading.Event()
        for _ in range(2):
            pool.submit(release_workers.wait)
        monkeypatch.setattr(live.routes, "_TURN_POOL", pool)
        live.routes.AGENT_TURN_TIMEOUT = 1.0
        live.agent.script_for = lambda sid, m: [thought("x")]
        threading.Timer(1.6, release_workers.set).start()

        try:
            with ThreadPoolExecutor(6) as ex:
                recs = list(
                    ex.map(
                        lambda i: run_turn(
                            live.base, f"s{i}", "m", fetch_result=False
                        ),
                        range(6),
                    )
                )
        finally:
            release_workers.set()
            pool.shutdown(wait=True)

        assert all(rec.got_done for rec in recs), [rec.error for rec in recs]
        worst = max(r.t_done - r.t_post for r in recs)
        assert worst < live.routes.AGENT_TURN_TIMEOUT + 0.5, (
            f"slowest queued turn needed {worst:.1f}s from POST to done "
            f"(timeout is {live.routes.AGENT_TURN_TIMEOUT}s)"
        )


# --------------------------------------------------------------------------- #
# The "retry" paths: reconnects, late connections, competing consumers
# --------------------------------------------------------------------------- #
def _open_stream(base, sid):
    c = httpx.Client(base_url=base, timeout=20)
    cm = c.stream("GET", f"/agent/stream/{sid}", headers=AUTH)
    resp = cm.__enter__()
    return c, cm, resp


def _post(base, sid, msg):
    with httpx.Client(base_url=base, timeout=10) as c:
        return c.post("/agent", data={"message": msg, "session_id": sid}, headers=AUTH)


class TestReconnectAndRetry:
    def test_connecting_after_the_turn_finished_returns_done_immediately(self, live):
        live.agent.script_for = lambda sid, m: [thought("x")]
        assert _post(live.base, "s1", "hi").status_code == 202
        deadline = time.time() + 5
        while not events.has_result("s1") and time.time() < deadline:
            time.sleep(0.02)
        t0 = time.monotonic()
        c, cm, r = _open_stream(live.base, "s1")
        try:
            names = [n for n, _ in parse_sse_lines(sse_lines(r))]
        finally:
            cm.__exit__(None, None, None)
            c.close()
        assert names[-1] == "done"
        assert time.monotonic() - t0 < 1.0
        assert c.is_closed

    def test_result_endpoint_is_idempotent_for_retries(self, live):
        live.agent.script_for = lambda sid, m: [thought("x")]
        run_turn(live.base, "s1", "hi")
        with httpx.Client(base_url=live.base, timeout=10) as c:
            bodies = [c.get("/agent/result/s1", headers=AUTH) for _ in range(5)]
        assert {b.status_code for b in bodies} == {200}
        assert len({b.text for b in bodies}) == 1

    def test_result_is_404_while_turn_is_still_running(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.8)]
        assert _post(live.base, "s1", "hi").status_code == 202
        with httpx.Client(base_url=live.base, timeout=10) as c:
            assert c.get("/agent/result/s1", headers=AUTH).status_code == 404

    def test_dropped_stream_then_reconnect_still_reaches_done(self, live):
        live.agent.script_for = lambda sid, m: [
            thought("t1"), sleep(0.5), thought("t2"), sleep(0.5), thought("t3"), sleep(0.3)
        ]
        assert _post(live.base, "s1", "hi").status_code == 202
        c1, cm1, r1 = _open_stream(live.base, "s1")
        first = next(parse_sse_lines(sse_lines(r1)))
        assert first[0] == "status"
        cm1.__exit__(None, None, None)  # connection dies mid-turn
        c1.close()

        c2, cm2, r2 = _open_stream(live.base, "s1")
        try:
            names = [n for n, _ in parse_sse_lines(sse_lines(r2))]
        finally:
            cm2.__exit__(None, None, None)
            c2.close()
        assert names[-1] == "done"
        with httpx.Client(base_url=live.base, timeout=10) as c:
            assert c.get("/agent/result/s1", headers=AUTH).json()["response"] == "answer-to:hi"

    def test_repeated_drops_and_reconnects_during_one_turn(self, live):
        live.agent.script_for = lambda sid, m: [thought(f"t{i}", delay=0.15) for i in range(10)]
        assert _post(live.base, "s1", "hi").status_code == 202
        got_done = False
        for _ in range(30):
            c, cm, r = _open_stream(live.base, "s1")
            try:
                for n, _ in parse_sse_lines(sse_lines(r)):
                    if n == "done":
                        got_done = True
                        break
                    break  # drop after the first event, then reconnect
            finally:
                cm.__exit__(None, None, None)
                c.close()
            if got_done:
                break
        assert got_done, "never saw done across 30 reconnects"

    def test_two_streams_on_the_same_session_both_terminate(self, live):
        """A queue is a competing-consumer structure (each event goes to ONE
        reader). The has_result fallback must still let both streams finish."""
        live.agent.script_for = lambda sid, m: [thought(f"t{i}", delay=0.1) for i in range(6)]
        assert _post(live.base, "s1", "hi").status_code == 202
        results = []

        def reader():
            c, cm, r = _open_stream(live.base, "s1")
            try:
                results.append([n for n, _ in parse_sse_lines(sse_lines(r))])
            finally:
                cm.__exit__(None, None, None)
                c.close()

        ts = [threading.Thread(target=reader) for _ in range(2)]
        [t.start() for t in ts]
        [t.join(timeout=15) for t in ts]
        assert len(results) == 2 and all(r[-1] == "done" for r in results), results

    def test_stream_for_unknown_session_is_404_not_a_hang(self, live):
        with httpx.Client(base_url=live.base, timeout=5) as c:
            assert c.get("/agent/stream/nope", headers=AUTH).status_code == 404

    def test_stream_requires_auth(self, live):
        with httpx.Client(base_url=live.base, timeout=5) as c:
            assert c.get("/agent/stream/s1").status_code == 401

    def test_stream_accepts_token_query_param_for_eventsource(self, live):
        live.agent.script_for = lambda sid, m: [thought("x")]
        assert _post(live.base, "s1", "hi").status_code == 202
        with httpx.Client(base_url=live.base, timeout=10) as c:
            with c.stream("GET", "/agent/stream/s1", params={"token": "abc"}) as r:
                assert r.status_code == 200
                assert [n for n, _ in parse_sse_lines(sse_lines(r))][-1] == "done"

    def test_keepalive_comments_are_sent_during_a_long_silence(self, live, monkeypatch):
        """Idle proxies kill silent connections; the stream must emit comments."""
        import asyncio

        real_sleep = asyncio.sleep
        # make the generator's 0.25s polling tick 50x faster so 15s of idle fits in 0.3s
        async def fast_sleep(delay, *a, **k):
            return await real_sleep(delay / 50, *a, **k)

        monkeypatch.setattr(live.routes.asyncio, "sleep", fast_sleep)
        live.agent.script_for = lambda sid, m: [sleep(0.6)]
        assert _post(live.base, "s1", "hi").status_code == 202
        raw = []
        with httpx.Client(base_url=live.base, timeout=10) as c:
            with c.stream("GET", "/agent/stream/s1", headers=AUTH) as r:
                raw = list(sse_lines(r))
        assert any(line.startswith(": keep-alive") for line in raw), raw

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (only if the frontend opens the stream BEFORE posting the next message): "
            "the previous turn's stored result is still there, so has_result() is True and "
            "the new stream closes at once with `done` -> the frontend then fetches the OLD "
            "answer. begin_turn() only runs inside POST /agent. A per-turn id in the stream "
            "URL / result would remove the ambiguity."
        ),
    )
    def test_stream_opened_before_the_next_post_does_not_end_with_the_old_turn(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.5)]
        run_turn(live.base, "s1", "first")
        c, cm, r = _open_stream(live.base, "s1")  # opened first, POST comes after
        try:
            time.sleep(0.2)
            _post(live.base, "s1", "second")
            names = []
            for n, _ in parse_sse_lines(sse_lines(r)):
                names.append(n)
        finally:
            cm.__exit__(None, None, None)
            c.close()
        with httpx.Client(base_url=live.base, timeout=10) as c2:
            answer = c2.get("/agent/result/s1", headers=AUTH)
        # the stream may only end once turn 2 is finished, so its answer is ready
        assert answer.status_code == 200 and answer.json()["response"] == "answer-to:second"


# --------------------------------------------------------------------------- #
# Concurrency rules of the endpoint
# --------------------------------------------------------------------------- #
class TestInFlightRules:
    def test_second_message_while_turn_runs_is_rejected_with_409(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.8)]
        assert _post(live.base, "s1", "a").status_code == 202
        assert _post(live.base, "s1", "b").status_code == 409

    def test_burst_of_simultaneous_posts_accepts_exactly_one(self, live):
        live.agent.script_for = lambda sid, m: [sleep(0.8)]
        with ThreadPoolExecutor(12) as ex:
            codes = list(ex.map(lambda i: _post(live.base, "s1", f"m{i}").status_code, range(12)))
        assert Counter(codes) == {202: 1, 409: 11}, Counter(codes)
        assert len(live.agent.invocations) == 1

    def test_follow_up_sent_the_instant_done_is_seen_is_never_rejected(self, live):
        """publish_done() runs BEFORE clear_in_flight(): a frontend that reacts to
        `done` immediately must not hit a 409."""
        live.agent.script_for = lambda sid, m: [thought("x")]

        def chatter(i):
            return [run_turn(live.base, f"s{i}", f"m{k}", fetch_result=False).post_status for k in range(10)]

        with ThreadPoolExecutor(20) as ex:
            codes = Counter(c for chunk in ex.map(chatter, range(20)) for c in chunk)
        assert codes == {202: 20 * 10}, codes

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: /agent/reset during a running turn deletes the session, but the "
            "background thread then runs save_state(final_state) and silently RESURRECTS "
            "it (and publishes done/result for a conversation the user just cleared)."
        ),
    )
    def test_reset_during_a_running_turn_is_not_undone_by_the_turn_finishing(self, live):
        live.agent.script_for = lambda sid, m: [thought("x"), sleep(0.8)]
        assert _post(live.base, "s1", "hi").status_code == 202
        time.sleep(0.2)
        with httpx.Client(base_url=live.base, timeout=10) as c:
            assert c.post("/agent/reset", data={"session_id": "s1"}, headers=AUTH).status_code == 200
        assert memory.load_state("s1") is None
        time.sleep(1.2)  # the turn thread finishes now
        assert memory.load_state("s1") is None, "session came back after reset"

    def test_reset_while_streaming_ends_the_stream(self, live):
        live.agent.script_for = lambda sid, m: [sleep(2.0)]
        assert _post(live.base, "s1", "hi").status_code == 202
        c, cm, r = _open_stream(live.base, "s1")
        try:
            time.sleep(0.3)
            with httpx.Client(base_url=live.base, timeout=10) as c2:
                c2.post("/agent/reset", data={"session_id": "s1"}, headers=AUTH)
            names = [n for n, _ in parse_sse_lines(sse_lines(r))]
        finally:
            cm.__exit__(None, None, None)
            c.close()
        assert names[-1] == "done"
