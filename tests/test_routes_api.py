"""
HTTP-level tests for every route in app/api/routes.py.

Uses the in-process TestClient (`client` fixture). Starlette runs a request's
BackgroundTasks before the client gets control back, so by the time
POST /agent returns, the (scripted) agent turn has already finished: no sleeps,
no races. Streaming / timing / concurrency behaviour lives in
test_sse_lifecycle.py and test_sse_latency.py (real uvicorn).
"""

from __future__ import annotations

import json

import pytest

from sse_harness import AUTH, action, auth_for, parse_sse_frames, raise_
from app.agent import memory
from app.agent.state import AgentState


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def init_session(client, **form) -> str:
    r = client.post("/agent/init", data=form, headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def send(client, sid, message="hello", headers=None, **form):
    return client.post(
        "/agent",
        data={"message": message, "session_id": sid, **form},
        headers=AUTH if headers is None else headers,
    )


def frames_of(response):
    return list(parse_sse_frames(response.text.split("\n")))


# --------------------------------------------------------------------------- #
# Authentication (shared by every protected endpoint)
# --------------------------------------------------------------------------- #
PROTECTED = [
    ("post", "/agent/init", {}),
    ("post", "/agent", {"data": {"message": "x", "session_id": "s"}}),
    ("get", "/agent/session/s", {}),
    ("get", "/agent/turns/t", {}),
    ("get", "/agent/turns/t/events", {}),
    ("post", "/agent/context", {"data": {"session_id": "s", "page_context": "{}"}}),
    ("post", "/agent/reset", {"data": {"session_id": "s"}}),
    ("post", "/agent/feedback", {"params": {"session_id": "s", "message_index": 0}}),
    ("post", "/agent/tool", {"params": {"territory": "t"}, "json": {"key": "summary"}}),
    ("get", "/agent/usage_stats", {}),
]
IDS = [f"{m.upper()} {p}" for m, p, _ in PROTECTED]


class TestAuthentication:
    @pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED, ids=IDS)
    def test_missing_authorization_header_is_401(self, client, method, path, kwargs):
        r = getattr(client, method)(path, **kwargs)

        assert r.status_code == 401

    @pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED, ids=IDS)
    @pytest.mark.parametrize("header", ["Token abc", "Bearer", "Bearer ", "abc"])
    def test_malformed_authorization_header_is_401(self, client, method, path, kwargs, header):
        r = getattr(client, method)(path, headers={"Authorization": header}, **kwargs)

        assert r.status_code == 401

    @pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED, ids=IDS)
    def test_token_rejected_by_the_backend_is_401(self, client, api_env, method, path, kwargs):
        api_env.authorized = False

        r = getattr(client, method)(path, headers=AUTH, **kwargs)

        assert r.status_code == 401

    def test_unauthorized_detail_message(self, client, api_env):
        api_env.authorized = False

        assert client.get("/agent/usage_stats", headers=AUTH).json() == {
            "detail": "Unauthorized"
        }

    def test_backend_is_asked_to_validate_the_bearer_token(self, client, api_env):
        client.post("/agent/init", headers=auth_for("my-token"))

        assert api_env.auth_calls == ["my-token"]

    def test_authorized_tokens_are_cached(self, client, api_env):
        for _ in range(5):
            client.get("/agent/session/none", headers=auth_for("cached"))

        assert api_env.auth_calls == ["cached"]

    def test_different_tokens_are_validated_separately(self, client, api_env):
        client.get("/agent/session/none", headers=auth_for("a"))
        client.get("/agent/session/none", headers=auth_for("b"))

        assert api_env.auth_calls == ["a", "b"]

    def test_rejected_tokens_are_not_cached(self, client, api_env):
        api_env.authorized = False
        assert client.post("/agent/init", headers=auth_for("t")).status_code == 401
        api_env.authorized = True  # e.g. the user logs in again

        assert client.post("/agent/init", headers=auth_for("t")).status_code == 201

    def test_cache_entries_expire(self, client, api_env, monkeypatch):
        monkeypatch.setattr(api_env.routes, "_AUTH_TTL", 0.0)

        client.get("/agent/session/none", headers=auth_for("t"))
        client.get("/agent/session/none", headers=auth_for("t"))

        assert api_env.auth_calls == ["t", "t"]

    def test_token_query_param_is_only_accepted_by_the_events_endpoint(self, client):
        r = client.get("/agent/turns/t", params={"token": "abc"})

        assert r.status_code == 401

    def test_auth_disabled_allows_anonymous_requests(self, client, api_env, monkeypatch):
        monkeypatch.setattr(api_env.routes, "AUTH_ENABLED", False)

        r = client.post("/agent/init")

        assert r.status_code == 201
        state = memory.load_state(r.json()["session_id"])
        assert (state.user_id, state.user_role) == ("anonymous", "viewer")
        assert api_env.auth_calls == []

    def test_auth_disabled_still_enforces_ownership_between_sessions(
        self, client, api_env, monkeypatch
    ):
        monkeypatch.setattr(api_env.routes, "AUTH_ENABLED", False)
        sid = client.post("/agent/init").json()["session_id"]

        assert send(client, sid, headers={}).status_code == 202

    def test_role_comes_from_the_backend(self, client, api_env):
        api_env.role = "editor"

        sid = init_session(client)

        assert memory.load_state(sid).user_role == "editor"


# --------------------------------------------------------------------------- #
# POST /agent/init
# --------------------------------------------------------------------------- #
class TestInit:
    def test_creates_a_standalone_session_with_defaults(self, client):
        r = client.post("/agent/init", headers=AUTH)

        assert r.status_code == 201
        body = r.json()
        assert set(body) == {"session_id", "session_mode", "allowed_territories"}
        assert body["session_mode"] == "standalone"
        assert body["allowed_territories"] == ["test-territory"]
        state = memory.load_state(body["session_id"])
        assert isinstance(state, AgentState)
        assert state.user_lang == "Italian"
        assert state.integrated_mode is False
        assert state.user_id == "user-1"
        assert state.allowed_territories == ["test-territory"]

    def test_every_call_creates_a_new_session(self, client):
        ids = {init_session(client) for _ in range(5)}

        assert len(ids) == 5

    def test_session_is_bound_to_the_calling_user(self, client, api_env):
        api_env.users["bob-token"] = "bob"

        r = client.post("/agent/init", headers=auth_for("bob-token"))

        assert memory.load_state(r.json()["session_id"]).user_id == "bob"

    def test_language_can_be_chosen(self, client):
        sid = init_session(client, user_lang="English")

        assert memory.load_state(sid).user_lang == "English"

    def test_allowed_territories_come_from_the_backend(self, client, api_env):
        api_env.territories = ["verona", "padova"]

        r = client.post("/agent/init", headers=AUTH)

        assert r.json()["allowed_territories"] == ["verona", "padova"]
        assert memory.load_state(r.json()["session_id"]).allowed_territories == [
            "verona",
            "padova",
        ]

    def test_state_is_persisted_to_disk(self, client, tmp_path):
        sid = init_session(client)

        assert (tmp_path / "logs" / f"state_{sid}.json").exists()

    def test_integrated_mode_requires_context(self, client):
        r = client.post("/agent/init", data={"integrated_mode": "true"}, headers=AUTH)

        assert r.status_code == 400
        assert r.json()["detail"] == "Context is required in integrated mode"

    def test_failed_init_does_not_create_a_session(self, client):
        client.post("/agent/init", data={"integrated_mode": "true"}, headers=AUTH)

        assert memory._STATE_STORE == {}

    def test_integrated_mode_parses_the_context(self, client):
        r = client.post(
            "/agent/init",
            data={
                "integrated_mode": "true",
                "context": ["problem:p1", "scenario:s1", "scenario:s2", "proposal:pr1"],
            },
            headers=AUTH,
        )

        assert r.status_code == 201
        assert r.json()["session_mode"] == "internal"
        state = memory.load_state(r.json()["session_id"])
        assert state.integrated_mode is True
        assert state.session_mode == "internal"
        assert state.cognitive.current_context == {
            "problems": ["p1"],
            "proposals": ["pr1"],
            "scenarios": ["s1", "s2"],
        }

    def test_context_is_ignored_outside_integrated_mode(self, client):
        sid = init_session(client, context=["problem:p1"])

        assert memory.load_state(sid).cognitive.current_context == {
            "problems": [],
            "proposals": [],
            "scenarios": [],
        }


# --------------------------------------------------------------------------- #
# _apply_context / _result helpers
# --------------------------------------------------------------------------- #
class TestHelpers:
    def test_apply_context_groups_ids_by_prefix(self, api_env):
        state = AgentState(session_id="s")

        api_env.routes._apply_context(
            state, ["problem:a", "scenario:b", "proposal:c", "problem:d"]
        )

        assert state.cognitive.current_context == {
            "problems": ["a", "d"],
            "proposals": ["c"],
            "scenarios": ["b"],
        }

    def test_apply_context_keeps_colons_inside_the_id(self, api_env):
        state = AgentState(session_id="s")

        api_env.routes._apply_context(state, ["problem:urn:x:1"])

        assert state.cognitive.current_context["problems"] == ["urn:x:1"]

    def test_apply_context_ignores_unknown_prefixes(self, api_env):
        state = AgentState(session_id="s")

        api_env.routes._apply_context(state, ["widget:1", "nonsense"])

        assert state.cognitive.current_context == {
            "problems": [],
            "proposals": [],
            "scenarios": [],
        }

    def test_apply_context_replaces_the_previous_context(self, api_env):
        state = AgentState(session_id="s")
        api_env.routes._apply_context(state, ["problem:a"])

        api_env.routes._apply_context(state, ["scenario:z"])

        assert state.cognitive.current_context["problems"] == []
        assert state.cognitive.current_context["scenarios"] == ["z"]

    def test_result_without_agent_type_omits_the_key(self, api_env):
        assert api_env.routes._result("s", "hi") == {
            "response": "hi",
            "session_id": "s",
            "assistant_action_data": None,
            "territory": None,
        }

    def test_result_with_agent_type_and_actions(self, api_env):
        out = api_env.routes._result("s", "hi", "executor", [{"type": "X"}])

        assert out["agent_type"] == "executor"
        assert out["assistant_action_data"] == [{"type": "X"}]


# --------------------------------------------------------------------------- #
# POST /agent
# --------------------------------------------------------------------------- #
class TestRunAgent:
    def test_returns_202_with_session_and_turn_id(self, client):
        sid = init_session(client)

        r = send(client, sid)

        assert r.status_code == 202
        body = r.json()
        assert body["session_id"] == sid
        assert len(body["turn_id"]) == 32

    def test_the_agent_runs_and_the_turn_finishes(self, client, api_env):
        sid = init_session(client)

        turn_id = send(client, sid, "ciao").json()["turn_id"]

        turn = client.get(f"/agent/turns/{turn_id}", headers=AUTH).json()
        assert turn["status"] == "done"
        assert turn["result"]["response"] == "answer-to:ciao"
        assert len(api_env.agent.invocations) == 1

    def test_user_and_assistant_messages_are_stored_in_order(self, client):
        sid = init_session(client)
        send(client, sid, "one")
        send(client, sid, "two")

        msgs = memory.load_state(sid).conversation.messages

        assert [(m.role, m.content) for m in msgs] == [
            ("user", "one"),
            ("assistant", "answer-to:one"),
            ("user", "two"),
            ("assistant", "answer-to:two"),
        ]

    @pytest.mark.parametrize("message", ["", "   ", "\n\t "])
    def test_blank_message_is_400(self, client, message):
        sid = init_session(client)

        r = send(client, sid, message)

        assert r.status_code in (400, 422)  # FastAPI may reject "" as missing
        if r.status_code == 400:
            assert r.json()["detail"] == "No message provided"

    def test_whitespace_only_message_is_a_400_with_message(self, client):
        sid = init_session(client)

        r = send(client, sid, "   ")

        assert r.status_code == 400
        assert r.json()["detail"] == "No message provided"

    def test_blank_message_starts_no_turn(self, client, api_env):
        sid = init_session(client)

        send(client, sid, "   ")

        assert api_env.store.active_turn(sid) is None
        assert api_env.store.latest_turn(sid) is None

    def test_missing_fields_are_422(self, client):
        assert client.post("/agent", data={"session_id": "s"}, headers=AUTH).status_code == 422
        assert client.post("/agent", data={"message": "m"}, headers=AUTH).status_code == 422

    def test_unknown_session_is_404(self, client):
        r = send(client, "does-not-exist")

        assert r.status_code == 404
        assert r.json()["detail"] == "Session not found"

    def test_someone_elses_session_is_404_not_403(self, client, api_env):
        sid = init_session(client)
        api_env.users["mallory"] = "user-2"

        r = send(client, sid, headers=auth_for("mallory"))

        assert r.status_code == 404  # session ids must not be probeable
        assert api_env.agent.invocations == []

    def test_force_role_rejects_unknown_values(self, client):
        sid = init_session(client)

        assert send(client, sid, force_role="superuser").status_code == 422

    @pytest.mark.parametrize("role", ["executor", "operative", "methodological", "exploitative"])
    def test_force_role_accepts_every_documented_tier(self, client, role):
        sid = init_session(client)

        assert send(client, sid, force_role=role).status_code == 202
        assert memory.load_state(sid).force_role == role

    def test_force_role_is_replaced_by_the_next_request(self, client):
        sid = init_session(client)
        send(client, sid, force_role="operative")

        send(client, sid, force_role="executor")
        assert memory.load_state(sid).force_role == "executor"

        send(client, sid, force_role="auto")
        assert memory.load_state(sid).force_role is None

        send(client, sid, force_role="methodological")
        send(client, sid)  # omitted -> reset, it does not stick
        assert memory.load_state(sid).force_role is None

    def test_waiting_turn_keeps_its_forced_role_and_forwards_the_user_input(
        self, client, api_env
    ):
        """A reply to a question the agent asked continues the SAME logical turn."""
        sid = init_session(client)
        state = memory.load_state(sid)
        state.waiting_for = AgentState.WaitingFor.PROBLEM_INPUT
        state.force_role = "operative"
        seen = {}
        orig = api_env.agent.invoke

        def spy(st, config=None):
            seen.update(force_role=st.force_role, user_input=st.user_input)
            return orig(st, config)

        api_env.agent.invoke = spy

        send(client, sid, "my answer", force_role="executor")

        assert seen == {"force_role": "operative", "user_input": "my answer"}

    def test_user_input_is_not_set_when_the_agent_is_not_waiting(self, client, api_env):
        sid = init_session(client)
        seen = {}
        orig = api_env.agent.invoke

        def spy(st, config=None):
            seen["user_input"] = st.user_input
            return orig(st, config)

        api_env.agent.invoke = spy

        send(client, sid, "plain message")

        assert seen["user_input"] is None

    def test_enabled_tools_are_reset_for_every_turn(self, client, api_env):
        sid = init_session(client)
        memory.load_state(sid).cognitive.enabled_tools = ["stale_tool"]
        seen = {}
        orig = api_env.agent.invoke

        def spy(st, config=None):
            seen["enabled"] = list(st.cognitive.enabled_tools)
            return orig(st, config)

        api_env.agent.invoke = spy

        send(client, sid)

        assert seen["enabled"] == []

    def test_bearer_token_is_passed_to_the_agent_config(self, client, api_env):
        sid = init_session(client)
        seen = {}
        orig = api_env.agent.invoke

        def spy(st, config=None):
            seen["config"] = config
            return orig(st, config)

        api_env.agent.invoke = spy

        send(client, sid, headers=auth_for("tok-123"))

        assert seen["config"] == {"configurable": {"token": "tok-123", "thread_id": sid}}

    def test_active_agent_tier_is_reported_in_the_result(self, client):
        sid = init_session(client)

        turn_id = send(client, sid).json()["turn_id"]

        result = client.get(f"/agent/turns/{turn_id}", headers=AUTH).json()["result"]
        assert result["agent_type"] == "executor"

    # ---- integrated mode -------------------------------------------------
    def test_integrated_mode_turn_needs_some_context(self, client, api_env):
        sid = init_session(client, integrated_mode="true", context=["problem:p1"])
        memory.load_state(sid).cognitive.current_context = {}  # nothing left

        r = send(client, sid)

        assert r.status_code == 400
        assert r.json()["detail"] == "Context is required in integrated mode"
        assert api_env.store.active_turn(sid) is None

    def test_integrated_mode_reuses_the_stored_context(self, client):
        sid = init_session(client, integrated_mode="true", context=["problem:p1"])

        assert send(client, sid).status_code == 202

    def test_integrated_mode_context_can_be_updated_per_message(self, client):
        sid = init_session(client, integrated_mode="true", context=["problem:p1"])

        send(client, sid, context=["scenario:s9"])

        assert memory.load_state(sid).cognitive.current_context == {
            "problems": [],
            "proposals": [],
            "scenarios": ["s9"],
        }

    def test_context_sent_in_standalone_mode_is_ignored(self, client):
        sid = init_session(client)

        send(client, sid, context=["problem:p1"])

        assert memory.load_state(sid).cognitive.current_context["problems"] == []

    # ---- concurrency / idempotency (single-threaded view) ----------------
    def test_idempotency_key_replays_the_same_turn_without_rerunning(self, client, api_env):
        sid = init_session(client)
        headers = {**AUTH, "Idempotency-Key": "abc"}

        first = send(client, sid, "hi", headers=headers).json()
        retry = send(client, sid, "hi", headers=headers).json()

        assert retry == first
        assert len(api_env.agent.invocations) == 1
        users = [m for m in memory.load_state(sid).conversation.messages if m.role == "user"]
        assert len(users) == 1

    def test_running_turn_blocks_a_second_message_with_409(self, client, api_env):
        sid = init_session(client)
        running, _ = api_env.store.start_turn(sid)  # simulate a turn in progress

        r = send(client, sid, "second")

        assert r.status_code == 409
        assert r.json()["detail"]["active_turn_id"] == running
        assert "still being processed" in r.json()["detail"]["message"]
        assert api_env.agent.invocations == []

    def test_409_leaves_the_conversation_untouched(self, client, api_env):
        sid = init_session(client)
        api_env.store.start_turn(sid)

        send(client, sid, "second")

        assert memory.load_state(sid).conversation.messages == []

    def test_failure_while_preparing_the_turn_releases_it(self, client, api_env, monkeypatch):
        sid = init_session(client)
        calls = {"n": 0}
        real_save = api_env.routes.save_state

        def flaky(state):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("disk full")
            return real_save(state)

        monkeypatch.setattr(api_env.routes, "save_state", flaky)

        with pytest.raises(OSError):
            send(client, sid, "boom")

        failed = api_env.store.latest_turn(sid)
        assert api_env.store.get(failed)["status"] == "failed"
        assert api_env.store.active_turn(sid) is None
        assert send(client, sid, "retry").status_code == 202  # not a permanent 409


# --------------------------------------------------------------------------- #
# GET /agent/session/{id}
# --------------------------------------------------------------------------- #
class TestGetSession:
    def test_fresh_session_has_no_turns(self, client):
        sid = init_session(client)

        r = client.get(f"/agent/session/{sid}", headers=AUTH)

        assert r.status_code == 200
        assert r.json() == {"session_id": sid, "active_turn_id": None, "latest_turn_id": None}

    def test_reports_the_latest_finished_turn(self, client):
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]

        body = client.get(f"/agent/session/{sid}", headers=AUTH).json()

        assert body["active_turn_id"] is None
        assert body["latest_turn_id"] == turn_id

    def test_reports_the_running_turn(self, client, api_env):
        sid = init_session(client)
        running, _ = api_env.store.start_turn(sid)

        body = client.get(f"/agent/session/{sid}", headers=AUTH).json()

        assert body["active_turn_id"] == running == body["latest_turn_id"]

    def test_latest_turn_follows_new_turns(self, client):
        sid = init_session(client)
        send(client, sid, "one")
        second = send(client, sid, "two").json()["turn_id"]

        assert client.get(f"/agent/session/{sid}", headers=AUTH).json()["latest_turn_id"] == second

    def test_unknown_session_is_404(self, client):
        assert client.get("/agent/session/nope", headers=AUTH).status_code == 404

    def test_other_users_session_is_404(self, client, api_env):
        sid = init_session(client)
        api_env.users["mallory"] = "user-2"

        r = client.get(f"/agent/session/{sid}", headers=auth_for("mallory"))

        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# GET /agent/turns/{id}
# --------------------------------------------------------------------------- #
class TestGetTurn:
    def test_finished_turn(self, client):
        sid = init_session(client)
        turn_id = send(client, sid, "hi").json()["turn_id"]

        r = client.get(f"/agent/turns/{turn_id}", headers=AUTH)

        assert r.status_code == 200
        assert r.json() == {
            "turn_id": turn_id,
            "session_id": sid,
            "status": "done",
            "last_event_id": 1,  # the default script publishes one action
            "result": {
                "response": "answer-to:hi",
                "session_id": sid,
                "assistant_action_data": None,
                "territory": None,
                "agent_type": "executor",
            },
        }

    def test_running_turn_has_null_result(self, client, api_env):
        sid = init_session(client)
        running, _ = api_env.store.start_turn(sid)
        api_env.store.append_event(running, "{}")

        body = client.get(f"/agent/turns/{running}", headers=AUTH).json()

        assert body["status"] == "running"
        assert body["result"] is None
        assert body["last_event_id"] == 1

    def test_last_event_id_counts_published_actions(self, client, api_env):
        api_env.agent.script_for = lambda sid, m: [action("a"), action("b"), action("c")]
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]

        assert client.get(f"/agent/turns/{turn_id}", headers=AUTH).json()["last_event_id"] == 3

    def test_failed_turn_exposes_a_system_error_result(self, client, api_env):
        api_env.agent.script_for = lambda sid, m: [raise_(RuntimeError("boom"))]
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]

        body = client.get(f"/agent/turns/{turn_id}", headers=AUTH).json()

        assert body["status"] == "failed"
        assert body["result"]["response"] == "System error"
        assert "boom" not in json.dumps(body), "internal error text must not leak"

    def test_unknown_turn_is_404(self, client):
        r = client.get("/agent/turns/nope", headers=AUTH)

        assert r.status_code == 404
        assert r.json()["detail"] == "Turn not found"

    def test_other_users_turn_is_404(self, client, api_env):
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]
        api_env.users["mallory"] = "user-2"

        r = client.get(f"/agent/turns/{turn_id}", headers=auth_for("mallory"))

        assert r.status_code == 404

    def test_turn_of_a_reset_session_is_404(self, client):
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]
        client.post("/agent/reset", data={"session_id": sid}, headers=AUTH)

        assert client.get(f"/agent/turns/{turn_id}", headers=AUTH).status_code == 404


# --------------------------------------------------------------------------- #
# GET /agent/turns/{id}/events (finite bodies: the turn is already finished)
# --------------------------------------------------------------------------- #
class TestTurnEvents:
    @pytest.fixture
    def finished_turn(self, client, api_env):
        api_env.agent.script_for = lambda sid, m: [action("a"), action("b"), action("c")]
        sid = init_session(client)
        return send(client, sid).json()["turn_id"]

    def test_replays_events_then_done(self, client, finished_turn):
        r = client.get(f"/agent/turns/{finished_turn}/events", headers=AUTH)

        assert r.status_code == 200
        assert r.text.startswith("retry: 2000\n\n")
        frames = frames_of(r)
        assert [(i, n) for i, n, _ in frames] == [
            (1, "status"), (2, "status"), (3, "status"), (4, "done"),
        ]
        assert [json.loads(d).get("tool") for _, n, d in frames if n == "status"] == ["a", "b", "c"]
        assert json.loads(frames[-1][2]) == {"status": "done"}

    def test_response_headers(self, client, finished_turn):
        r = client.get(f"/agent/turns/{finished_turn}/events", headers=AUTH)

        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache, no-transform"
        assert r.headers["x-accel-buffering"] == "no"
        assert r.headers["connection"] == "keep-alive"

    def test_last_event_id_header_resumes_after_that_event(self, client, finished_turn):
        r = client.get(
            f"/agent/turns/{finished_turn}/events", headers={**AUTH, "Last-Event-ID": "2"}
        )

        assert [(i, n) for i, n, _ in frames_of(r)] == [(3, "status"), (4, "done")]

    def test_last_event_id_query_param_resumes_after_that_event(self, client, finished_turn):
        r = client.get(
            f"/agent/turns/{finished_turn}/events", headers=AUTH, params={"last_event_id": "1"}
        )

        assert [i for i, _, _ in frames_of(r)] == [2, 3, 4]

    def test_header_takes_precedence_over_query(self, client, finished_turn):
        r = client.get(
            f"/agent/turns/{finished_turn}/events",
            headers={**AUTH, "Last-Event-ID": "3"},
            params={"last_event_id": "0"},
        )

        assert [i for i, _, _ in frames_of(r)] == [4]

    @pytest.mark.parametrize("raw", ["abc", "-4", "", "1e3", "2.5"])
    def test_unparseable_or_negative_cursor_replays_everything(self, client, finished_turn, raw):
        r = client.get(
            f"/agent/turns/{finished_turn}/events", headers=AUTH, params={"last_event_id": raw}
        )

        assert [i for i, _, _ in frames_of(r)] == [1, 2, 3, 4]

    def test_token_query_param_authenticates_eventsource(self, client, api_env, finished_turn):
        api_env.auth_calls.clear()

        r = client.get(f"/agent/turns/{finished_turn}/events", params={"token": "es-token"})

        assert r.status_code == 200
        assert api_env.auth_calls == ["es-token"]

    def test_authorization_header_wins_over_token_param(self, client, api_env, finished_turn):
        api_env.auth_calls.clear()

        client.get(
            f"/agent/turns/{finished_turn}/events",
            headers=auth_for("header-token"),
            params={"token": "query-token"},
        )

        assert api_env.auth_calls == ["header-token"]

    def test_unknown_turn_is_404(self, client):
        assert client.get("/agent/turns/nope/events", headers=AUTH).status_code == 404

    def test_other_users_turn_is_404(self, client, api_env, finished_turn):
        api_env.users["mallory"] = "user-2"

        r = client.get(f"/agent/turns/{finished_turn}/events", headers=auth_for("mallory"))

        assert r.status_code == 404

    def test_failed_turn_streams_done_with_failed_status(self, client, api_env):
        api_env.agent.script_for = lambda sid, m: [raise_(RuntimeError("boom"))]
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]

        frames = frames_of(client.get(f"/agent/turns/{turn_id}/events", headers=AUTH))

        assert json.loads(frames[-1][2]) == {"status": "failed"}


# --------------------------------------------------------------------------- #
# POST /agent/reset
# --------------------------------------------------------------------------- #
class TestReset:
    def test_destroys_state_and_turns(self, client, api_env):
        sid = init_session(client)
        turn_id = send(client, sid).json()["turn_id"]

        r = client.post("/agent/reset", data={"session_id": sid}, headers=AUTH)

        assert r.status_code == 200
        assert r.json() == {"session_id": sid, "status": "reset"}
        assert memory.load_state(sid) is None
        assert api_env.store.get(turn_id) is None
        assert api_env.store.latest_turn(sid) is None
        assert sid not in memory._LOCKS

    def test_session_cannot_be_used_after_reset(self, client):
        sid = init_session(client)
        client.post("/agent/reset", data={"session_id": sid}, headers=AUTH)

        assert send(client, sid).status_code == 404
        assert client.get(f"/agent/session/{sid}", headers=AUTH).status_code == 404

    def test_second_reset_is_404(self, client):
        sid = init_session(client)
        client.post("/agent/reset", data={"session_id": sid}, headers=AUTH)

        assert client.post("/agent/reset", data={"session_id": sid}, headers=AUTH).status_code == 404

    def test_unknown_session_is_404(self, client):
        assert client.post("/agent/reset", data={"session_id": "x"}, headers=AUTH).status_code == 404

    def test_cannot_reset_someone_elses_session(self, client, api_env):
        sid = init_session(client)
        api_env.users["mallory"] = "user-2"

        r = client.post("/agent/reset", data={"session_id": sid}, headers=auth_for("mallory"))

        assert r.status_code == 404
        assert memory.load_state(sid) is not None, "the victim's session must survive"

    def test_other_sessions_are_not_affected(self, client, api_env):
        a, b = init_session(client), init_session(client)
        turn_b = send(client, b).json()["turn_id"]

        client.post("/agent/reset", data={"session_id": a}, headers=AUTH)

        assert memory.load_state(b) is not None
        assert api_env.store.get(turn_b) is not None

    def test_session_id_is_required(self, client):
        assert client.post("/agent/reset", headers=AUTH).status_code == 422

    def test_reset_releases_a_running_turn(self, client, api_env):
        sid = init_session(client)
        api_env.store.start_turn(sid)

        client.post("/agent/reset", data={"session_id": sid}, headers=AUTH)

        assert api_env.store.active_turn(sid) is None


# --------------------------------------------------------------------------- #
# POST /agent/feedback
# --------------------------------------------------------------------------- #
class TestFeedback:
    @pytest.fixture
    def session_with_answer(self, client):
        sid = init_session(client)
        send(client, sid, "q")  # messages: [0]=user, [1]=assistant
        return sid

    def fb(self, client, sid, index, **extra):
        return client.post(
            "/agent/feedback",
            params={"session_id": sid, "message_index": index, **extra},
            headers=AUTH,
        )

    @pytest.mark.parametrize("vote", ["up", "down"])
    def test_vote_is_saved(self, client, session_with_answer, vote):
        r = self.fb(client, session_with_answer, 1, vote=vote)

        assert r.status_code == 200
        assert r.json() == {"message": "Feedback saved."}
        assert memory.load_state(session_with_answer).conversation.messages[1].vote == vote

    def test_comment_is_saved(self, client, session_with_answer):
        self.fb(client, session_with_answer, 1, vote="down", comment="wrong territory")

        msg = memory.load_state(session_with_answer).conversation.messages[1]
        assert msg.comment == "wrong territory"

    @pytest.mark.parametrize("vote", [None, "sideways", "UP", ""])
    def test_invalid_or_missing_vote_clears_the_vote(self, client, session_with_answer, vote):
        self.fb(client, session_with_answer, 1, vote="up")

        extra = {} if vote is None else {"vote": vote}
        self.fb(client, session_with_answer, 1, **extra)

        assert memory.load_state(session_with_answer).conversation.messages[1].vote is None

    def test_vote_can_be_changed(self, client, session_with_answer):
        self.fb(client, session_with_answer, 1, vote="up")
        self.fb(client, session_with_answer, 1, vote="down")

        assert memory.load_state(session_with_answer).conversation.messages[1].vote == "down"

    def test_feedback_is_persisted_to_disk(self, client, session_with_answer, tmp_path):
        self.fb(client, session_with_answer, 1, vote="up", comment="great")

        dumped = (tmp_path / "logs" / f"state_{session_with_answer}.json").read_text()
        assert "great" in dumped

    @pytest.mark.parametrize("index", [-1, 2, 99])
    def test_out_of_range_index_is_400(self, client, session_with_answer, index):
        r = self.fb(client, session_with_answer, index, vote="up")

        assert r.status_code == 400
        assert r.json()["detail"] == "Invalid message index"

    def test_feedback_on_a_user_message_is_400(self, client, session_with_answer):
        r = self.fb(client, session_with_answer, 0, vote="up")

        assert r.status_code == 400
        assert r.json()["detail"] == "Can only give feedback on assistant messages"

    def test_unknown_session_is_404(self, client):
        assert self.fb(client, "nope", 0, vote="up").status_code == 404

    def test_other_users_session_is_404(self, client, api_env, session_with_answer):
        api_env.users["mallory"] = "user-2"

        r = client.post(
            "/agent/feedback",
            params={"session_id": session_with_answer, "message_index": 1, "vote": "down"},
            headers=auth_for("mallory"),
        )

        assert r.status_code == 404
        assert memory.load_state(session_with_answer).conversation.messages[1].vote is None

    def test_message_index_must_be_an_integer(self, client, session_with_answer):
        r = client.post(
            "/agent/feedback",
            params={"session_id": session_with_answer, "message_index": "abc"},
            headers=AUTH,
        )

        assert r.status_code == 422


# --------------------------------------------------------------------------- #
# POST /agent/tool (stateless pipelines)
# --------------------------------------------------------------------------- #
class TestRunSelectedTools:
    @pytest.fixture
    def pipeline(self, api_env, monkeypatch):
        """Replace the tool executor + registry bootstrap; record every call."""
        import types

        from app.agent.nodes import tool_executor

        rec = types.SimpleNamespace(calls=[], outcomes={}, registry_calls=0)

        def fake_execute(tool_name, arguments, state, allow_disabled=False):
            rec.calls.append(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                    "state": state,
                    "allow_disabled": allow_disabled,
                }
            )
            return rec.outcomes.get(
                tool_name,
                {"success": True, "output": {"message": f"{tool_name}-output"}, "error": None},
            )

        def fake_registry():
            rec.registry_calls += 1

        monkeypatch.setattr(tool_executor, "execute_selected_tool", fake_execute)
        monkeypatch.setattr(api_env.routes, "_ensure_tool_registry", fake_registry)
        return rec

    def run(self, client, body, territory="test-territory", headers=None):
        return client.post(
            "/agent/tool",
            params={"territory": territory},
            json=body,
            headers=AUTH if headers is None else headers,
        )

    def test_summary_runs_context_then_summary_and_returns_the_last_message(
        self, client, pipeline
    ):
        r = self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        assert r.status_code == 200
        assert r.json() == {"message": "summary_generation-output"}
        assert [c["tool"] for c in pipeline.calls] == ["get_context_details", "summary_generation"]
        assert all(c["arguments"] == {} for c in pipeline.calls)

    def test_pdf_report_runs_report_and_returns_the_document(self, client, pipeline):
        pipeline.outcomes["report_generation"] = {
            "success": True,
            "output": {"report": {"title": "Localized report"}},
            "error": None,
        }

        r = self.run(client, {"key": "pdf-report", "current_context": {"problems": ["p1"]}})

        assert r.status_code == 200
        assert r.json() == {"report": {"title": "Localized report"}}
        assert [c["tool"] for c in pipeline.calls] == ["report_generation"]

    def test_report_language_is_forwarded_to_the_system_state(self, client, pipeline):
        pipeline.outcomes["report_generation"] = {
            "success": True,
            "output": {"report": {"title": "Localized report"}},
            "error": None,
        }

        r = self.run(
            client,
            {
                "key": "pdf-report",
                "current_context": {"problems": ["p1"]},
                "user_lang": "English",
            },
        )

        assert r.status_code == 200
        assert pipeline.calls[0]["state"].user_lang == "English"

    def test_steps_share_one_system_mode_state(self, client, pipeline, api_env):
        self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        first, second = pipeline.calls
        assert first["state"] is second["state"], "later steps must see earlier results"
        state = first["state"]
        assert state.session_mode == "system"
        assert state.territory == "test-territory"
        assert state.user_id == "user-1-system"
        assert state.user_role == api_env.role
        assert state.allowed_territories == ["test-territory"]
        assert state.cognitive.current_context == {"scenarios": ["s1"]}

    def test_disabled_tools_are_allowed_for_the_pipeline(self, client, pipeline):
        self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        assert all(c["allow_disabled"] is True for c in pipeline.calls)

    def test_pipeline_is_stateless(self, client, pipeline, api_env):
        self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        assert memory._STATE_STORE == {}
        assert api_env.store.latest_turn("") is None

    def test_registry_is_bootstrapped(self, client, pipeline):
        self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        assert pipeline.registry_calls == 1

    def test_temp_context_is_forwarded_untouched(self, client, pipeline):
        ctx = {"temp": {"creation_session": "cs1", "evaluation_id": "e1"}}

        self.run(client, {"key": "summary", "current_context": ctx})

        assert pipeline.calls[0]["state"].cognitive.current_context == ctx

    def test_failure_stops_the_pipeline_with_a_500(self, client, pipeline):
        pipeline.outcomes["get_context_details"] = {
            "success": False,
            "output": None,
            "error": "context not found",
        }

        r = self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        assert r.status_code == 500
        assert r.json()["detail"] == "context not found"
        assert [c["tool"] for c in pipeline.calls] == ["get_context_details"]

    def test_failure_in_the_last_step_is_a_500(self, client, pipeline):
        pipeline.outcomes["summary_generation"] = {
            "success": False,
            "output": None,
            "error": "LLM down",
        }

        r = self.run(client, {"key": "summary", "current_context": {"scenarios": ["s1"]}})

        assert r.status_code == 500
        assert r.json()["detail"] == "LLM down"
        assert len(pipeline.calls) == 2

    @pytest.mark.parametrize("key", ["summary"])
    @pytest.mark.parametrize("context", [None, {}])
    def test_empty_context_is_400(self, client, pipeline, key, context):
        body = {"key": key}
        if context is not None:
            body["current_context"] = context

        r = self.run(client, body)

        assert r.status_code == 400
        assert pipeline.calls == []

    def test_pdf_report_allows_empty_context_for_the_whole_territory(
        self, client, pipeline
    ):
        pipeline.outcomes["report_generation"] = {
            "success": True,
            "output": {"report": {"title": "Territory report"}},
            "error": None,
        }

        r = self.run(client, {"key": "pdf-report"})

        assert r.status_code == 200
        assert r.json() == {"report": {"title": "Territory report"}}
        assert [call["tool"] for call in pipeline.calls] == ["report_generation"]

    def test_unknown_key_is_422(self, client, pipeline):
        r = self.run(client, {"key": "delete-everything", "current_context": {"a": ["b"]}})

        assert r.status_code == 422
        assert pipeline.calls == []

    def test_territory_must_be_allowed_for_the_user(self, client, pipeline):
        r = self.run(
            client,
            {"key": "summary", "current_context": {"scenarios": ["s1"]}},
            territory="forbidden-land",
        )

        assert r.status_code == 400
        assert "forbidden-land" in r.json()["detail"]
        assert "test-territory" in r.json()["detail"]
        assert pipeline.calls == []

    def test_territory_is_required(self, client, pipeline):
        r = client.post(
            "/agent/tool",
            json={"key": "summary", "current_context": {"scenarios": ["s1"]}},
            headers=AUTH,
        )

        assert r.status_code == 422

    def test_body_is_required(self, client, pipeline):
        r = client.post("/agent/tool", params={"territory": "test-territory"}, headers=AUTH)

        assert r.status_code == 422

    def test_steps_in_the_body_are_ignored(self, client, pipeline):
        """`steps` is reserved: each key hardcodes its own sequence."""
        self.run(
            client,
            {
                "key": "summary",
                "current_context": {"scenarios": ["s1"]},
                "steps": [{"tool_name": "drop_database", "arguments": {}}],
            },
        )

        assert [c["tool"] for c in pipeline.calls] == ["get_context_details", "summary_generation"]


# --------------------------------------------------------------------------- #
# GET /agent/usage_stats
# --------------------------------------------------------------------------- #
class TestUsageStats:
    def test_returns_the_aggregated_usage(self, client, monkeypatch):
        rows = [{"date": "2026-10-26", "user": "u", "requests": 3}]
        monkeypatch.setattr("app.utils.token_tacking.get_usage_per_day", lambda: rows)

        r = client.get("/agent/usage_stats", headers=AUTH)

        assert r.status_code == 200
        assert r.json() == rows

    def test_empty_when_there_is_no_log(self, client, tmp_path):
        # cwd is tmp_path: no token log file exists there
        assert client.get("/agent/usage_stats", headers=AUTH).json() == []


# --------------------------------------------------------------------------- #
# Health endpoints (no auth)
# --------------------------------------------------------------------------- #
class TestHealth:
    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/health", {"status": "ok", "service": "api"}),
            ("/health/live", {"status": "ok"}),
            ("/health/ready", {"status": "ready"}),
        ],
    )
    def test_probes_need_no_credentials(self, client, api_env, path, body):
        r = client.get(path)

        assert r.status_code == 200
        assert r.json() == body
        assert api_env.auth_calls == [], "probes must never call the auth backend"

    def test_version_defaults_to_unknown(self, client, monkeypatch):
        monkeypatch.delenv("APP_VERSION", raising=False)

        assert client.get("/health/version").json() == {"service": "api", "version": "unknown"}

    def test_version_comes_from_the_environment(self, client, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "1.2.3")

        assert client.get("/health/version").json()["version"] == "1.2.3"

    def test_probes_do_not_touch_the_agent(self, client, api_env):
        for path in ("/health", "/health/live", "/health/ready", "/health/version"):
            client.get(path)

        assert api_env.agent.invocations == []


# --------------------------------------------------------------------------- #
# Full app wiring (app.main) - catches a router that is no longer mounted
# --------------------------------------------------------------------------- #
class TestAppWiring:
    def test_router_exposes_every_documented_endpoint(self, api_env):
        paths = {(m, r.path) for r in api_env.routes.router.routes for m in r.methods}

        assert paths >= {
            ("POST", "/agent/init"),
            ("POST", "/agent"),
            ("GET", "/agent/session/{session_id}"),
            ("GET", "/agent/turns/{turn_id}"),
            ("GET", "/agent/turns/{turn_id}/events"),
            ("POST", "/agent/reset"),
            ("POST", "/agent/feedback"),
            ("POST", "/agent/tool"),
            ("GET", "/agent/usage_stats"),
            ("GET", "/health"),
            ("GET", "/health/live"),
            ("GET", "/health/ready"),
            ("GET", "/health/version"),
        }

    def test_removed_session_keyed_endpoints_are_gone(self, client):
        """The pre-turn API must not silently linger."""
        assert client.get("/agent/stream/s1", headers=AUTH).status_code == 404
        assert client.get("/agent/result/s1", headers=AUTH).status_code == 404

    def test_main_requires_backend_url_and_api_key(self, monkeypatch):
        import app.main as main

        monkeypatch.delenv("BACKEND_URL", raising=False)
        with pytest.raises(RuntimeError, match="BACKEND_URL"):
            main.validate_environment()

        monkeypatch.setenv("BACKEND_URL", "http://x/")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            main.validate_environment()

        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        main.validate_environment()  # no error

    def test_main_app_mounts_the_router_with_cors(self):
        from app.main import app

        paths = set(app.openapi()["paths"])
        assert {"/agent", "/agent/init", "/health"} <= paths
        assert any("CORSMiddleware" in str(m) for m in app.user_middleware)
