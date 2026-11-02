"""
"Why does the answer reach the frontend several seconds after it was generated?"

Timeline of one turn, and which test measures which hop:

    answer generated            (ScriptedAgent.invoke returns)           t0
      |  AgentState(**dict), store.finish(before_commit=remember_state)
    turn is terminal            (result stored, session released)         t1
      |  persist_state() -> dump_to_file() runs AFTER finish <-- A: slow JSON dump
      |  SSE generator polls the event list every 0.25 s     <-- B: up to 250 ms
      |  event loop must be free to run the generator        <-- C: sync `requests` calls
    client receives `done`                                                t2
      |  GET /agent/turns/{id} -> token cache / auth/me       <-- D
    client has the answer                                                 t3

A  test_done_is_not_delayed_by_state_persistence
B  test_baseline_*
C  test_event_loop_is_not_blocked_by_slow_backend_calls (+ the slow-dump variant)
D  test_result_fetch_does_not_wait_for_a_backend_auth_roundtrip

The latency tests assert that the delays above stay bounded under simulated
slow persistence and backend calls.
"""

from __future__ import annotations

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

import sse_harness as h
from sse_harness import AUTH, action, auth_for, call, run_turn, sleep
from app.agent import events, memory
from app.agent.state import AgentState


def _record_answer_ready(live):
    marks: dict[str, float] = {}
    live.agent.on_invoke_returned = lambda sid, t: marks.__setitem__(sid, t)
    return marks


def _turn_just_finished(state: AgentState) -> bool:
    last = state.get_last_message()
    return bool(last and last.role == "assistant")


class TestBaseline:
    def test_answer_to_done_latency_is_small_when_nothing_is_slow(self, live):
        marks = _record_answer_ready(live)
        live.agent.script_for = lambda sid, m: [action("x")]
        lat = []
        for i in range(15):
            rec = run_turn(live.base, f"s{i}", "hi")
            lat.append(rec.t_done - marks[f"s{i}"])
        print(f"\nanswer->done: median={statistics.median(lat)*1000:.0f}ms max={max(lat)*1000:.0f}ms")
        assert statistics.median(lat) < 0.4  # polling interval is 250 ms
        assert max(lat) < 0.8

    def test_done_to_answer_in_hand_is_small_when_auth_is_fast(self, live):
        live.agent.script_for = lambda sid, m: [action("x")]
        lat = []
        for i in range(10):
            rec = run_turn(live.base, f"s{i}", "hi")
            lat.append(rec.t_result - rec.t_done)
        print(f"\ndone->result: median={statistics.median(lat)*1000:.0f}ms max={max(lat)*1000:.0f}ms")
        assert max(lat) < 0.5

    def test_each_event_reaches_the_client_quickly_with_many_streams_open(self, live):
        """p95 publish->client lag for 40 simultaneous streams."""
        published: dict[str, float] = {}
        real_append = live.store.append_event

        def spy(turn_id, payload):
            published[payload] = time.monotonic()
            return real_append(turn_id, payload)

        live.store.append_event = spy
        live.agent.script_for = lambda sid, m: [
            action(f"{sid}-{i}", delay=0.05) for i in range(10)
        ]

        with ThreadPoolExecutor(40) as ex:
            recs = list(
                ex.map(
                    lambda i: run_turn(live.base, f"s{i}", "m", fetch_result=False), range(40)
                )
            )
        lags = []
        for rec in recs:
            for t, name, data in rec.sse_events:
                if name == "status" and data in published:
                    lags.append(t - published[data])
        lags.sort()
        p95 = lags[int(len(lags) * 0.95)]
        print(
            f"\nevent lag over {len(lags)} events: p50={statistics.median(lags)*1000:.0f}ms "
            f"p95={p95*1000:.0f}ms max={lags[-1]*1000:.0f}ms"
        )
        assert len(lags) == 400
        assert p95 < 0.6


class TestAnswerReadyToDone:
    def test_done_is_not_delayed_by_state_persistence(self, live, monkeypatch):
        marks = _record_answer_ready(live)
        orig = AgentState.dump_to_file

        def slow_dump(self, path):
            if _turn_just_finished(self):
                time.sleep(1.0)  # stands in for a big state / slow disk
            return orig(self, path)

        monkeypatch.setattr(AgentState, "dump_to_file", slow_dump)
        live.agent.script_for = lambda sid, m: [action("x")]
        rec = run_turn(live.base, "s1", "hi")
        lat = rec.t_done - marks["s1"]
        print(f"\nanswer->done with 1.0s state dump: {lat:.2f}s")
        assert lat < 0.6, f"`done` reached the client {lat:.2f}s after the answer was ready"

    def test_state_is_visible_to_next_turn_by_the_time_done_is_seen(self, live):
        """Safety net for the fix above: whatever order you persist in, the NEXT
        /agent call (which load_state()s) must already see this turn's answer."""
        live.agent.script_for = lambda sid, m: [action("x")]
        for i in range(10):
            rec = run_turn(live.base, "s1", f"m{i}", fetch_result=False)
            assert rec.got_done
            state = memory.load_state("s1")
            assert state.get_last_message().content == f"answer-to:m{i}", f"turn {i}: stale state"


class TestEventLoopBlocking:
    """Slow auth/backend calls and state writes must not freeze SSE streams."""

    def _run_victim_and_aggressors(self, live, aggressor):
        """Turn `victim` emits an event every 100 ms for ~2 s. Meanwhile three
        other clients run `aggressor`. Returns (victim_record, max_gap_between_events)."""
        marks = _record_answer_ready(live)
        live.agent.script_for = lambda sid, m: [action(f"t{i}", delay=0.1) for i in range(20)]
        out = {}
        victim = threading.Thread(
            target=lambda: out.setdefault("rec", run_turn(live.base, "victim", "m"))
        )
        victim.start()
        time.sleep(0.5)
        aggressors = [threading.Thread(target=aggressor, args=(i,)) for i in range(3)]
        [t.start() for t in aggressors]
        [t.join() for t in aggressors]
        victim.join()
        rec = out["rec"]
        times = [t for t, n, _ in rec.sse_events if n == "status"]
        gap = max(b - a for a, b in zip(times, times[1:]))
        return rec, gap, rec.t_done - marks["victim"]

    def test_event_loop_is_not_blocked_by_slow_backend_calls(self, live):
        def aggressor(i):
            # a NEW token every call: the 30 s token cache would otherwise turn
            # all but the first into instant hits and nothing would be slow
            with httpx.Client(base_url=live.base, timeout=30) as c:
                for k in range(3):
                    c.get(
                        "/agent/turns/does-not-exist",
                        headers=auth_for(f"agg-{i}-{k}"),
                    )

        # the victim's own POST + stream-open are fast; the backend only becomes
        # slow once its stream is running
        threading.Timer(0.45, lambda: setattr(live, "auth_delay", 0.8)).start()
        rec, gap, lat = self._run_victim_and_aggressors(live, aggressor)
        print(f"\nvictim: largest gap between events={gap:.2f}s (script: 0.10s); answer->done={lat:.2f}s")
        assert gap < 0.6, f"victim stream froze for {gap:.2f}s while others made auth calls"

    def test_event_loop_is_not_blocked_by_saving_state_on_init(self, live, monkeypatch):
        orig = AgentState.dump_to_file

        def slow_dump(self, path):
            if not _turn_just_finished(self):  # the dump done by POST /agent
                time.sleep(0.8)
            return orig(self, path)

        def aggressor(i):
            # /agent/init saves a brand-new state (-> slow dump_to_file)
            with httpx.Client(base_url=live.base, timeout=30) as c:
                assert c.post("/agent/init", headers=AUTH).status_code == 201

        # victim's own POST must not be slowed: install the slow dump after it started
        threading.Timer(0.45, lambda: monkeypatch.setattr(AgentState, "dump_to_file", slow_dump)).start()
        rec, gap, lat = self._run_victim_and_aggressors(live, aggressor)
        print(f"\nvictim: largest gap between events={gap:.2f}s (script: 0.10s)")
        assert gap < 0.6, f"victim stream froze for {gap:.2f}s while others created sessions"


class TestDoneToAnswerInHand:
    def test_result_fetch_does_not_wait_for_a_backend_auth_roundtrip(self, live):
        """The token was validated when the turn started; the 30 s cache must
        make the final GET /agent/turns/{id} independent of a now-slow backend."""
        live.agent.script_for = lambda sid, m: [
            call(lambda: setattr(live, "auth_delay", 0.8)),  # backend gets slow mid-turn
            action("x"),
        ]
        rec = run_turn(live.base, "s1", "hi")
        lat = rec.t_result - rec.t_done
        print(f"\ndone->result with a 0.8s auth backend: {lat:.2f}s")
        assert rec.result_status == 200
        assert rec.done_payload == {"status": "done"}
        assert lat < 0.4, f"answer arrived {lat:.2f}s after `done`"
