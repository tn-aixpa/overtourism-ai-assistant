"""
Behavioural tests for tool executors that had no dedicated coverage:
entity listing, scenario preview/promotion, widgets, system utilities and the
CRUD argument mapping. Backends (HTTP) and LLM calls are replaced by recording
fakes, so these check what OUR code does with them: which arguments it sends,
how it reacts to failures, what it stores in state and what it returns.
"""

import pytest

from app.agent.nodes import tool_executor as te
from app.agent.state import AgentState
from app.tools import executor_backend_tools as backend
from app.tools.executors import analysis_widgets as aw
from app.tools.executors import entities as entities_exec
from app.tools.executors import problem as problem_exec
from app.tools.executors import proposal as proposal_exec
from app.tools.executors import scenario as scenario_exec
from app.tools.executors import system_utility as su
from app.tools.tool_registry import _ensure_tool_registry


class FakeTool:
    """Stand-in for a langchain @tool: records .invoke() payloads."""

    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, []

    def invoke(self, payload):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.result() if callable(self.result) else self.result


@pytest.fixture
def state() -> AgentState:
    return AgentState(
        session_id="s",
        territory="molveno",
        allowed_territories=["molveno"],
        user_role="editor",
        session_mode="standalone",
    )


def fake(monkeypatch, module, name, **kw) -> FakeTool:
    tool = FakeTool(**kw)
    monkeypatch.setattr(module, name, tool)
    return tool


# ---------------------------------------------------------------------------
# list_available_entities
# ---------------------------------------------------------------------------


class TestListAvailableEntities:
    def _fakes(self, monkeypatch, **errors):
        return {
            kind: fake(
                monkeypatch, backend, f"get_all_{kind}",
                result=[{"id": f"{kind}-1"}], error=errors.get(kind),
            )
            for kind in ("problems", "proposals", "scenarios")
        }

    def test_default_returns_all_three_lists_for_the_session_territory(
        self, monkeypatch, state
    ):
        fakes = self._fakes(monkeypatch)
        out = entities_exec.execute_list_available_entities(state)
        assert set(out) == {"problems", "proposals", "scenarios"}
        for f in fakes.values():
            assert f.calls == [{"territory": "molveno"}]

    def test_only_requested_types_are_fetched(self, monkeypatch, state):
        fakes = self._fakes(monkeypatch)
        out = entities_exec.execute_list_available_entities(state, entity_types=["problems"])
        assert set(out) == {"problems"}
        assert fakes["proposals"].calls == [] and fakes["scenarios"].calls == []

    def test_singular_and_legacy_names_are_understood(self, monkeypatch, state):
        self._fakes(monkeypatch)
        out = entities_exec.execute_list_available_entities(
            state, entity_types=["proposal", "list_available_scenarios"]
        )
        assert set(out) == {"proposals", "scenarios"}

    def test_partial_failure_returns_the_rest_and_names_what_is_missing(
        self, monkeypatch, state
    ):
        self._fakes(monkeypatch, proposals=RuntimeError("backend 500"))
        out = entities_exec.execute_list_available_entities(state)
        assert out["unavailable"] == ["proposals"]
        assert "proposals" not in out and "problems" in out and "scenarios" in out
        assert "backend 500" not in str(out)  # detail stays in the logs

    def test_total_failure_raises_so_the_turn_reports_an_error(self, monkeypatch, state):
        self._fakes(
            monkeypatch,
            problems=RuntimeError("x"), proposals=RuntimeError("x"), scenarios=RuntimeError("x"),
        )
        with pytest.raises(RuntimeError, match="Could not retrieve"):
            entities_exec.execute_list_available_entities(state)

    def test_legacy_tool_names_go_through_the_same_wrapper(self, monkeypatch, state):
        """A persisted session may still call list_available_problems."""
        _ensure_tool_registry()
        self._fakes(monkeypatch)
        result = te.execute_selected_tool("list_available_problems", {}, state)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# CRUD argument mapping (territory always comes from state, never the model)
# ---------------------------------------------------------------------------


class TestCrudExecutorsMapArguments:
    def test_create_problem(self, monkeypatch, state):
        f = fake(monkeypatch, backend, "create_new_problem", result={"ok": 1})
        out = problem_exec.execute_create_new_problem(
            state, name="Traffic", description="d", objective="o", additional_data="x"
        )
        assert out == {"ok": 1}
        assert f.calls == [{
            "territory": "molveno", "name": "Traffic", "description": "d",
            "objective": "o", "additional_data": "x",
        }]

    def test_edit_and_delete_problem(self, monkeypatch, state):
        edit = fake(monkeypatch, backend, "edit_problem", result={})
        delete = fake(monkeypatch, backend, "delete_problem", result={})
        problem_exec.execute_edit_problem(state, problem_id="p1", name="N")
        problem_exec.execute_delete_problem(state, problem_id="p1")
        assert edit.calls[0]["problem_id"] == "p1" and edit.calls[0]["territory"] == "molveno"
        assert delete.calls == [{"problem_id": "p1", "territory": "molveno"}]

    def test_create_proposal(self, monkeypatch, state):
        f = fake(monkeypatch, backend, "create_new_proposal", result={})
        proposal_exec.execute_create_new_proposal(
            state, name="P", problem_id="p1", description="d",
            resources="r", context="c", impact="i",
        )
        assert f.calls == [{
            "territory": "molveno", "name": "P", "problem_id": "p1", "description": "d",
            "resources": "r", "context": "c", "impact": "i",
        }]

    def test_edit_and_delete_scenario(self, monkeypatch, state):
        edit = fake(monkeypatch, backend, "edit_scenario", result={})
        delete = fake(monkeypatch, backend, "delete_scenario", result={})
        scenario_exec.execute_edit_scenario(state, scenario_id="s1", name="N", description="D")
        scenario_exec.execute_delete_scenario(state, scenario_id="s1")
        assert edit.calls == [{"territory": "molveno", "scenario_id": "s1", "name": "N", "description": "D"}]
        assert delete.calls == [{"scenario_id": "s1", "territory": "molveno"}]

    @pytest.mark.parametrize("executor,backend_tool,args", [
        (problem_exec.execute_create_new_problem, "create_new_problem",
         {"name": "N", "description": "d"}),
        (problem_exec.execute_edit_problem, "edit_problem", {"problem_id": "p1"}),
        (problem_exec.execute_delete_problem, "delete_problem", {"problem_id": "p1"}),
        (proposal_exec.execute_create_new_proposal, "create_new_proposal",
         {"name": "N", "problem_id": "p1"}),
        (scenario_exec.execute_edit_scenario, "edit_scenario", {"scenario_id": "s1"}),
        (scenario_exec.execute_delete_scenario, "delete_scenario", {"scenario_id": "s1"}),
        (scenario_exec.execute_get_base_scenario, "get_base_scenario", {}),
    ])
    def test_model_supplied_territory_cannot_override_the_session_territory(
        self, monkeypatch, state, executor, backend_tool, args
    ):
        """The model must never be able to point a write at another territory."""
        f = fake(monkeypatch, backend, backend_tool, result={})
        try:
            executor(state, **args, territory="someone-else")
        except TypeError:
            return  # executor rejects the unknown argument outright: also safe
        assert f.calls and all(c["territory"] == "molveno" for c in f.calls)

    def test_get_base_scenario_uses_session_territory(self, monkeypatch, state):
        f = fake(monkeypatch, backend, "get_base_scenario", result="base-1")
        assert scenario_exec.execute_get_base_scenario(state) == "base-1"
        assert f.calls == [{"territory": "molveno"}]


# ---------------------------------------------------------------------------
# create_new_temp_scenario / create_new_scenario
# ---------------------------------------------------------------------------


@pytest.fixture
def scenario_env(monkeypatch):
    """Everything create_new_temp_scenario talks to, faked."""
    env = type("Env", (), {})()
    env.widgets = fake(monkeypatch, backend, "get_widgets", result={"indexes": []})
    env.base = fake(monkeypatch, backend, "get_base_scenario", result="base-1")
    env.session = fake(monkeypatch, backend, "create_cration_session", result="sess-1")
    env.temp = fake(
        monkeypatch, backend, "create_temp_scenario",
        result={"scenario_id": "tmp-1", "evaluation_id": "ev-1",
                "creation_session": "sess-1", "data": {"kpi": 1}},
    )
    env.promote = fake(monkeypatch, backend, "promote_scenario", result={"saved": True})
    env.resolution = {
        "problems": [], "payload": {"parking_users": 3},
        "changes": [{"summary": "parking_users: 2 -> 3"}],
    }
    monkeypatch.setattr(scenario_exec, "load_indexes", lambda raw: "INDEXES")
    monkeypatch.setattr(scenario_exec, "resolve_overrides", lambda idx, values: env.resolution)
    env.widget_calls = []

    def build_load_plot_result(state, scenario_id, scenario_result):
        env.widget_calls.append(scenario_id)
        return {"assistant_action_data": [{"type": "SHOW_WIDGET", "id": scenario_id}]}

    monkeypatch.setattr(aw, "build_load_plot_result", build_load_plot_result)
    return env


class TestCreateNewTempScenario:
    def test_empty_values_are_rejected_before_any_backend_call(self, scenario_env, state):
        with pytest.raises(ValueError, match="at least one parameter"):
            scenario_exec.execute_create_new_temp_scenario(state, values={})
        assert scenario_env.temp.calls == []

    def test_success_creates_stores_pending_and_shows_widget_in_standalone(
        self, scenario_env, state
    ):
        out = scenario_exec.execute_create_new_temp_scenario(state, values={"parking_users": 3})
        assert out["created"] is True and out["temporary"] is True
        assert out["scenario_id"] == "tmp-1" and out["base_scenario_id"] == "base-1"
        assert out["values"] == {"parking_users": 3}  # the RESOLVED payload is what is sent
        assert scenario_env.temp.calls[0]["values"] == {"parking_users": 3}
        assert scenario_env.temp.calls[0]["creation_session"] == "sess-1"
        assert out["assistant_action_data"][0]["type"] == "SHOW_WIDGET"
        assert state.cognitive.pending_temp_scenario["scenario_id"] == "tmp-1"
        assert state.cognitive.pending_temp_scenario["evaluation_id"] == "ev-1"

    def test_internal_mode_does_not_build_a_widget(self, scenario_env, state):
        state.session_mode = "internal"
        out = scenario_exec.execute_create_new_temp_scenario(state, values={"parking_users": 3})
        assert out["created"] is True
        assert "assistant_action_data" not in out
        assert scenario_env.widget_calls == []

    def test_explicit_base_scenario_skips_the_lookup(self, scenario_env, state):
        out = scenario_exec.execute_create_new_temp_scenario(
            state, values={"a": 1}, base_scenario_id="my-base"
        )
        assert out["base_scenario_id"] == "my-base"
        assert scenario_env.base.calls == []

    def test_existing_creation_session_is_reused(self, scenario_env, state):
        state.integrated_context = {"creation_session": "host-session"}
        scenario_exec.execute_create_new_temp_scenario(state, values={"a": 1})
        assert scenario_env.session.calls == []
        assert scenario_env.temp.calls[0]["creation_session"] == "host-session"

    def test_only_one_temp_scenario_at_a_time(self, scenario_env, state):
        state.cognitive.pending_temp_scenario = {
            "scenario_id": "old", "creation_session": "sess-old",
            "changes": [{"summary": "x: 1 -> 2"}],
        }
        out = scenario_exec.execute_create_new_temp_scenario(state, values={"a": 1})
        assert out["created"] is False and out["already_pending"] is True
        assert out["pending_scenario_id"] == "old"
        assert scenario_env.temp.calls == []
        assert state.cognitive.pending_temp_scenario["scenario_id"] == "old"

    def test_replace_pending_discards_the_old_one(self, scenario_env, state):
        state.cognitive.pending_temp_scenario = {
            "scenario_id": "old", "creation_session": "sess-old", "changes": [],
        }
        out = scenario_exec.execute_create_new_temp_scenario(
            state, values={"a": 1}, replace_pending=True
        )
        assert out["created"] is True
        assert state.cognitive.pending_temp_scenario["scenario_id"] == "tmp-1"
        # the preview session of the old one is reused, not recreated
        assert scenario_env.temp.calls[0]["creation_session"] == "sess-old"

    def test_invalid_values_create_nothing_and_report_problems(self, scenario_env, state):
        scenario_env.resolution = {"problems": ["parking_users: out of range"], "payload": {}, "changes": []}
        out = scenario_exec.execute_create_new_temp_scenario(state, values={"parking_users": 999})
        assert out["created"] is False
        assert out["problems"] == ["parking_users: out of range"]
        assert scenario_env.temp.calls == []
        assert state.cognitive.pending_temp_scenario is None

    def test_values_equal_to_current_ones_are_a_no_op(self, scenario_env, state):
        scenario_env.resolution = {"problems": [], "payload": {}, "changes": []}
        out = scenario_exec.execute_create_new_temp_scenario(state, values={"parking_users": 2})
        assert out["created"] is False and "nothing different" in out["message"]
        assert scenario_env.temp.calls == []


class TestCreateNewScenario:
    @pytest.fixture(autouse=True)
    def _summary(self, monkeypatch):
        from app.tools import pipelines

        self.summary_calls = []
        monkeypatch.setattr(
            pipelines, "generate_temp_scenario_summary",
            lambda st, session, evaluation: self.summary_calls.append((session, evaluation)) or "SUMMARY",
        )

    def _pending(self, state):
        state.cognitive.pending_temp_scenario = {
            "scenario_id": "tmp-1", "evaluation_id": "ev-1", "creation_session": "sess-1",
        }

    def test_without_a_preview_it_fails_loudly(self, scenario_env, state):
        with pytest.raises(ValueError, match="No temporary scenario"):
            scenario_exec.execute_create_new_scenario(state, name="N")
        assert scenario_env.promote.calls == []

    def test_promotes_the_pending_scenario_with_its_summary_and_consumes_it(
        self, scenario_env, state
    ):
        self._pending(state)
        out = scenario_exec.execute_create_new_scenario(
            state, name="Plan A", description="d", proposal_id="pr1"
        )
        assert out == {"saved": True}
        assert scenario_env.promote.calls == [{
            "territory": "molveno", "creation_session": "sess-1", "scenario_id": "tmp-1",
            "name": "Plan A", "description": "d", "proposal_id": "pr1", "summary": "SUMMARY",
        }]
        assert self.summary_calls == [("sess-1", "ev-1")]
        assert state.cognitive.pending_temp_scenario is None
        with pytest.raises(ValueError):  # cannot be saved twice
            scenario_exec.execute_create_new_scenario(state, name="again")

    def test_failed_promotion_keeps_the_pending_scenario_so_save_can_be_retried(
        self, scenario_env, state
    ):
        self._pending(state)
        scenario_env.promote.error = RuntimeError("backend down")
        with pytest.raises(RuntimeError):
            scenario_exec.execute_create_new_scenario(state, name="Plan A")
        assert state.cognitive.pending_temp_scenario["scenario_id"] == "tmp-1"


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class TestAnalysisWidgets:
    @pytest.fixture
    def widget_env(self, monkeypatch):
        env = type("Env", (), {})()
        env.payload = {"scenarios s1": {"kpi": 1}, "scenarios s2": {"kpi": 2}}
        monkeypatch.setattr(aw, "_get_evaluation_payload", lambda st, ids: {
            k: v for k, v in env.payload.items() if k.split()[1] in ids
        })
        monkeypatch.setattr(
            aw, "build_widget_payload",
            lambda st, ids, data, subsystem: {"payload": {"scenarioIds": ids}, "subsystem": subsystem},
        )
        return env

    @pytest.mark.parametrize("widget_type,widget_name,count", [
        ("load_plot", "loadPlot", 1),
        ("capacity_plot", "capacityPlot", 1),
        ("kpi_comparison", "indexComparison", 2),
        ("comparison_plot", "histogramComparison", 2),
    ])
    def test_each_widget_type_emits_the_right_frontend_widget(
        self, widget_env, state, widget_type, widget_name, count
    ):
        out = aw.execute_analysis_widget(state, widget_type, scenario_ids=["s1", "s2"])
        action = out["assistant_action_data"][0]
        assert out["success"] is True
        assert action["type"] == "SHOW_WIDGET"
        assert action["payload"]["widgetName"] == widget_name
        assert action["payload"]["data"]["payload"]["scenarioIds"] == ["s1", "s2"][:count]

    def test_unknown_widget_type_raises(self, widget_env, state):
        with pytest.raises(ValueError, match="Unknown widget_type"):
            aw.execute_analysis_widget(state, "pie_chart", scenario_ids=["s1"])

    def test_too_few_scenarios_says_nothing_was_shown(self, widget_env, state):
        out = aw.execute_analysis_widget(state, "kpi_comparison", scenario_ids=["s1"])
        assert out["success"] is False and out["shown"] is False
        assert "NOT be shown" in out["response"] and "assistant_action_data" not in out

    def test_scenarios_fall_back_to_the_resolved_context(self, widget_env, state):
        state.cognitive.current_context = {"scenarios": ["s2"]}
        out = aw.execute_analysis_widget(state, "load_plot")
        assert out["assistant_action_data"][0]["payload"]["data"]["payload"]["scenarioIds"] == ["s2"]

    def test_missing_evaluation_data_is_reported_not_faked(self, widget_env, state):
        out = aw.execute_analysis_widget(state, "load_plot", scenario_ids=["ghost"])
        assert out["success"] is False and out["shown"] is False

    def test_widget_already_queued_for_a_temp_scenario_is_not_duplicated(
        self, widget_env, state
    ):
        state.cognitive.pending_temp_scenario = {"scenario_id": "s1"}
        state.assistant_action_data = [{
            "type": "SHOW_WIDGET",
            "payload": {"widgetName": "loadPlot", "data": {"payload": {"scenarioIds": ["s1"]}}},
        }]
        out = aw.execute_analysis_widget(state, "load_plot", scenario_ids=["s1"])
        assert out["success"] is True and "already being shown" in out["response"]
        assert "assistant_action_data" not in out

    @pytest.mark.parametrize("widget_type", ["load_plot", "capacity_plot", "comparison_plot"])
    def test_explain_widget_is_static_and_backend_free(self, state, widget_type):
        out = aw.execute_explain_widget(state, widget_type)
        assert out["success"] is True and len(out["message"]) > 40

    def test_explain_widget_rejects_unknown_types(self, state):
        with pytest.raises(ValueError, match="Unknown widget_type"):
            aw.execute_explain_widget(state, "kpi_comparison_xyz")


# ---------------------------------------------------------------------------
# System utilities
# ---------------------------------------------------------------------------


class TestSystemUtilityTools:
    def test_get_system_capabilities_returns_the_description(self, state):
        out = su.execute_get_system_capabilities(state)
        assert out["success"] is True and out["system_description"].strip()

    @pytest.mark.parametrize("route,expected", [
        (None, "modeling"),
        ([], "modeling"),
        (["index_methodology"], "territorial_indexes"),
    ])
    def test_explain_workflow_auto_selection(self, monkeypatch, state, route, expected):
        from app.utils import workflow_knowledge as wk

        monkeypatch.setattr(wk, "get_workflow_document", lambda kind: f"DOC:{kind}")
        state.cognitive.second_level_route = route
        out = su.execute_explain_workflow(state)
        assert out["success"] and out["workflow_type"] == expected
        assert out["workflow_document"] == f"DOC:{expected}"

    def test_explicit_workflow_type_beats_auto_selection(self, monkeypatch, state):
        from app.utils import workflow_knowledge as wk

        monkeypatch.setattr(wk, "get_workflow_document", lambda kind: f"DOC:{kind}")
        state.cognitive.second_level_route = ["index_methodology"]
        out = su.execute_explain_workflow(state, workflow_type="modeling")
        assert out["workflow_type"] == "modeling"

    def test_unknown_workflow_type_fails_cleanly(self, state):
        out = su.execute_explain_workflow(state, workflow_type="astrology")
        assert out["success"] is False and "Unknown workflow type" in out["error"]

    def test_missing_workflow_document_fails_cleanly(self, monkeypatch, state):
        from app.utils import workflow_knowledge as wk

        monkeypatch.setattr(wk, "get_workflow_document", lambda kind: "")
        out = su.execute_explain_workflow(state, workflow_type="modeling")
        assert out["success"] is False and "unavailable" in out["error"]

    def test_web_search_delegates_to_the_native_search_with_the_query(self, monkeypatch, state):
        from app.utils import llm

        seen = {}
        monkeypatch.setattr(llm, "native_web_search",
                            lambda st, q: seen.setdefault("q", q) and {"success": True, "answer": "a"})
        assert su.execute_web_search(state, "overtourism Dolomites")["success"]
        assert seen["q"] == "overtourism Dolomites"

    def test_general_question_response_wraps_the_generated_answer(self, monkeypatch, state):
        from app.prompts import answer_generation

        monkeypatch.setattr(answer_generation, "generate_answer", lambda st: "free-form answer")
        out = su.execute_general_question_response(state, query="what is carrying capacity?")
        assert out == {"success": True, "query": "what is carrying capacity?", "answer": "free-form answer"}


# ---------------------------------------------------------------------------
# Through the real dispatcher: gates that must hold for EVERY tool
# ---------------------------------------------------------------------------


class TestDispatcherGates:
    def test_viewer_cannot_run_a_write_tool(self, monkeypatch, state):
        _ensure_tool_registry()
        state.user_role = "viewer"
        f = fake(monkeypatch, backend, "delete_problem", result={})
        with pytest.raises(PermissionError):
            te.execute_selected_tool("delete_problem", {"problem_id": "p1"}, state)
        assert f.calls == []

    def test_widget_tool_is_refused_in_internal_mode(self, state):
        _ensure_tool_registry()
        state.session_mode = "internal"
        with pytest.raises(PermissionError):
            te.execute_selected_tool("show_analysis_widget", {"widget_type": "load_plot"}, state)

    def test_territory_scoped_tool_refuses_an_unallowed_territory(self, monkeypatch, state):
        _ensure_tool_registry()
        state.territory = "not-allowed"
        f = fake(monkeypatch, backend, "get_base_scenario", result="x")
        with pytest.raises(ValueError, match="requires a territory"):
            te.execute_selected_tool("get_base_scenario", {}, state)
        assert f.calls == []

    def test_forced_executor_role_blocks_exploitative_tools(self, monkeypatch, state):
        _ensure_tool_registry()
        state.force_role = "executor"
        with pytest.raises(PermissionError, match="not allowed for forced role"):
            te.execute_selected_tool("general_question_response", {"query": "q"}, state)

    def test_executor_failure_is_wrapped_not_raised(self, monkeypatch, state):
        _ensure_tool_registry()
        fake(monkeypatch, backend, "get_base_scenario", error=RuntimeError("boom"))
        result = te.execute_selected_tool("get_base_scenario", {}, state)
        assert result["success"] is False and "boom" in result["error"]
