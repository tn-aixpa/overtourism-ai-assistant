"""
Tier 1 — deterministic routing tests.

These test *your code*: given a fixed (mocked) LLM decision, does
react_reasoner_node route to the right place, enforce the enabled-tools
allowlist, and handle malformed/hallucinated responses safely? No real
Anthropic calls are made — see test_reasoner_eval.py for that.
"""

import json
from unittest.mock import patch

import pytest
from langgraph.types import Command

from app.agent.nodes import reasoner as reasoner_module
from app.agent.nodes import router as router_module
from app.agent.nodes import route_groups
from app.agent.state import AgentState, ReActStep
from app.prompts import react_reasoning as react_reasoning_module
from app.prompts.react_guidelines import GUIDELINE_BLOCKS, UNIVERSAL_POST
from app.tools.definitions.analysis import (
    create_get_configuration_parameters_tool,
    create_get_context_tool,
)
from app.tools.definitions.analysis_widgets import create_analysis_widget_tool
from app.tools.definitions.indexes import (
    create_get_territorial_index_list_tool,
    create_query_territorial_index_values_tool,
    create_show_territorial_index_map_tool,
    create_show_territorial_index_plot_tool,
)
from app.tools.tool_registry import get_tool_registry
from app.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter
from app.utils.page_context import render_page_context_block


def register_tool(name, params=None):
    tool = ToolDefinition(
        name=name,
        description="d",
        category=ToolCategory.UTILITY,
        parameters=params or [],
    )
    get_tool_registry().register_tool(tool)
    return tool


def react_step_response(**overrides):
    payload = {"thought": "reasoning...", "action": "finish", "message": "done"}
    payload.update(overrides)
    return json.dumps(payload)


def test_scenario_guidelines_require_preview_plot_and_respect_viewer_permissions():
    scenario_guidelines = "\n".join(
        body for _, body in GUIDELINE_BLOCKS["scenario_analysis"]
    )

    assert "After create_new_temp_scenario returns created=true" in scenario_guidelines
    assert "widget_type='load_plot'" in scenario_guidelines
    assert "do not offer saving as an option" in scenario_guidelines
    assert (
        "Do NOT call a write tool, ask for a name/description/proposal"
        in scenario_guidelines
    )


def test_existing_scenario_questions_always_include_evaluation_and_plot():
    scenario_guidelines = "\n".join(
        body for _, body in GUIDELINE_BLOCKS["scenario_analysis"]
    )

    assert "ALWAYS assume a request about an existing scenario" in scenario_guidelines
    assert (
        "call analyze_scenario_results to report its evaluation" in scenario_guidelines
    )
    assert "For a SINGLE existing scenario" in scenario_guidelines
    assert "widget_type='load_plot'" in scenario_guidelines


def test_base_scenario_aliases_are_explicitly_equivalent():
    scenario_guidelines = "\n".join(
        body for _, body in GUIDELINE_BLOCKS["scenario_analysis"]
    )

    for phrase in (
        "scenario di riferimento",
        "scenario base",
        "situazione attuale",
        "scenario as-is",
        "situazione as-is",
    ):
        assert phrase in scenario_guidelines
    assert "get_base_scenario first" in scenario_guidelines


def test_territory_catalog_has_a_direct_no_tool_route():
    assert route_groups.SUB_TERRITORY in route_groups.sublevel_options(
        route_groups.TOP_LOCATION
    )
    assert route_groups.resolve_allowed_tools(
        route_groups.TOP_LOCATION, route_groups.SUB_TERRITORY
    ) == set()
    assert route_groups.guideline_groups(
        route_groups.TOP_LOCATION, route_groups.SUB_TERRITORY
    ) == {"territory"}
    territory_guidelines = "\n".join(
        body for _, body in GUIDELINE_BLOCKS["territory"]
    )
    for phrase in ("località", "destinations", "territori"):
        assert phrase in territory_guidelines


def test_broad_scenario_list_uses_page_territory_without_relationship_target():
    relationships = next(
        body for title, body in GUIDELINE_BLOCKS["scenario_analysis"]
        if title == "RELATIONSHIPS BETWEEN PROBLEMS, PROPOSALS AND SCENARIOS"
    )
    page_policy = "\n".join(body for _, body in UNIVERSAL_POST)

    assert "entities.territory" in relationships
    assert "list_available_entities(entity_types=['scenarios'])" in page_policy
    assert "authorized selected territory" in page_policy


def test_territorial_index_guidelines_do_not_import_modelling_territories():
    index_guidelines = "\n".join(
        body
        for _, body in GUIDELINE_BLOCKS["indexes"]
    )

    assert "Keep index geography separate from the active modelling/scenario territory" in index_guidelines
    assert "Do not introduce place names from modelling context" in index_guidelines
    assert "Molveno" not in index_guidelines
    assert "Fazzon" not in index_guidelines


def test_internal_route_exposes_page_enrichment_tools_but_not_map_widgets():
    scenario_tools = route_groups.resolve_allowed_tools(
        route_groups.TOP_LOCATION, route_groups.SUB_SCENARIO
    )
    index_tools = route_groups.resolve_allowed_tools(
        route_groups.TOP_INDEXES, route_groups.SUB_INDEX_QUERY
    )

    assert {
        "get_configuration_parameters",
        "get_context_details",
    }.issubset(scenario_tools)
    assert {
        "get_territorial_index_list",
        "query_territorial_index_values",
    }.issubset(index_tools)
    assert create_get_configuration_parameters_tool().is_allowed_for("viewer", "internal")
    assert create_get_context_tool().is_allowed_for("viewer", "internal")
    assert create_get_territorial_index_list_tool().is_allowed_for("viewer", "internal")
    assert create_query_territorial_index_values_tool().is_allowed_for("viewer", "internal")
    assert not create_show_territorial_index_map_tool().is_allowed_for("viewer", "internal")
    assert not create_show_territorial_index_plot_tool().is_allowed_for("viewer", "internal")


def test_page_enrichment_fallback_still_asks_when_snapshot_has_no_entities():
    state = AgentState(integrated_mode=True)
    state.page_context = {"route": "/scenario", "elements": []}

    rendered = render_page_context_block(state)
    universal_post = "\n".join(body for _, body in UNIVERSAL_POST)

    assert "(none captured)" in rendered
    assert "Ask the user only if identifiers are missing" in rendered
    assert "finish with one short clarifying question" in universal_post


# ---------------------------------------------------------------------------
# initialize_tools
# ---------------------------------------------------------------------------


class TestInitializeTools:
    @pytest.mark.parametrize(
        ("force_role", "expected_tools", "expected_agent"),
        [
            (
                None,
                {"executor", "operative", "methodological", "exploitative"},
                "executor",
            ),
            (
                "auto",
                {"executor", "operative", "methodological", "exploitative"},
                "executor",
            ),
            ("executor", {"executor"}, "executor"),
            ("operative", {"executor", "operative"}, "operative"),
            ("methodological", {"methodological"}, "methodological"),
            ("exploitative", {"exploitative"}, "exploitative"),
        ],
    )
    def test_force_role_filters_agent_tiers(
        self, fresh_state: AgentState, force_role, expected_tools, expected_agent
    ):
        for tier in ("executor", "operative", "methodological", "exploitative"):
            get_tool_registry().register_tool(
                ToolDefinition(
                    name=tier,
                    description="d",
                    category=ToolCategory.UTILITY,
                    agent_tier=tier,
                )
            )

        fresh_state.force_role = force_role
        reasoner_module.initialize_tools(fresh_state)

        assert set(fresh_state.cognitive.enabled_tools) == expected_tools
        assert fresh_state.active_agent.value == expected_agent

    def test_changing_force_role_can_widen_back_to_all_known_tools(
        self, fresh_state: AgentState
    ):
        for tier in ("executor", "operative", "methodological", "exploitative"):
            get_tool_registry().register_tool(
                ToolDefinition(
                    name=tier,
                    description="d",
                    category=ToolCategory.UTILITY,
                    agent_tier=tier,
                )
            )

        fresh_state.force_role = "operative"
        reasoner_module.initialize_tools(fresh_state)
        assert set(fresh_state.cognitive.enabled_tools) == {"executor", "operative"}

        fresh_state.force_role = "methodological"
        reasoner_module.initialize_tools(fresh_state)

        assert set(fresh_state.cognitive.enabled_tools) == {"methodological"}
        assert set(fresh_state.cognitive.known_tools) == {
            "executor",
            "operative",
            "methodological",
            "exploitative",
        }

    def test_topic_router_preserves_forced_role_filter(self, fresh_state: AgentState):
        for name, tier in (
            ("get_system_capabilities", "executor"),
            ("lookup_glossary", "executor"),
            ("explain_workflow", "methodological"),
        ):
            get_tool_registry().register_tool(
                ToolDefinition(
                    name=name,
                    description="d",
                    category=ToolCategory.UTILITY,
                    agent_tier=tier,
                )
            )
        fresh_state.force_role = "methodological"
        fresh_state.cognitive.known_tools = [
            "get_system_capabilities",
            "lookup_glossary",
            "explain_workflow",
        ]

        router_module._apply_route(fresh_state, "system_info", None)

        assert fresh_state.cognitive.enabled_tools == ["explain_workflow"]

    def test_registers_default_tools_when_registry_empty(self, fresh_state: AgentState):
        assert get_tool_registry().list_tool_names() == []
        reasoner_module.initialize_tools(fresh_state)
        assert len(get_tool_registry().list_tool_names()) > 0

    def test_does_not_reregister_if_already_populated(self, fresh_state: AgentState):
        register_tool("custom_only_tool")
        reasoner_module.initialize_tools(fresh_state)
        # Registration is guarded by "if registry is empty" — since it
        # already had one tool, the real default toolset (e.g.
        # "lookup_glossary") must NOT have been added alongside it.
        names = get_tool_registry().list_tool_names()
        assert names == ["custom_only_tool"]

    def test_non_integrated_mode_enables_all_known_tools(self, fresh_state: AgentState):
        register_tool("a")
        register_tool("b")
        fresh_state.integrated_mode = False
        result = reasoner_module.initialize_tools(fresh_state)
        assert set(fresh_state.cognitive.enabled_tools) == {"a", "b"}
        assert result.goto == "top_level_router"

    def test_integrated_mode_preserves_preset_enabled_tools(
        self, fresh_state: AgentState
    ):
        register_tool("a")
        register_tool("b")
        fresh_state.integrated_mode = True
        fresh_state.cognitive.enabled_tools = ["a"]  # route already restricted this
        reasoner_module.initialize_tools(fresh_state)
        assert fresh_state.cognitive.enabled_tools == ["a"]

    def test_widget_tools_are_visible_in_standalone_and_hidden_in_integrated_mode(
        self, fresh_state: AgentState
    ):
        get_tool_registry().register_tool(create_analysis_widget_tool())

        fresh_state.integrated_mode = False
        fresh_state.session_mode = "standalone"
        reasoner_module.initialize_tools(fresh_state)
        assert "show_analysis_widget" in fresh_state.cognitive.enabled_tools

        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = ["a"]
        reasoner_module.initialize_tools(fresh_state)
        assert "show_analysis_widget" not in fresh_state.cognitive.enabled_tools

    def test_territorial_index_map_is_available_in_standalone_mode(
        self, fresh_state: AgentState
    ):
        get_tool_registry().register_tool(create_show_territorial_index_map_tool())

        fresh_state.integrated_mode = False
        reasoner_module.initialize_tools(fresh_state)

        assert "show_territorial_index_map" in fresh_state.cognitive.enabled_tools

        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = ["show_territorial_index_map"]
        reasoner_module.initialize_tools(fresh_state)

        assert "show_territorial_index_map" not in fresh_state.cognitive.enabled_tools

    def test_resets_scratchpad_and_pending_action_on_fresh_turn(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.scratchpad = [ReActStep(tool_name="x")]
        fresh_state.cognitive.selected_tool = "x"
        fresh_state.cognitive.tool_arguments = {"a": 1}
        fresh_state.cognitive.pending_thought = "old thought"
        fresh_state.cognitive.tool_confirmation_needed = True
        fresh_state.cognitive.tool_confirmed = True

        reasoner_module.initialize_tools(fresh_state)

        assert fresh_state.cognitive.scratchpad == []
        assert fresh_state.cognitive.selected_tool is None
        assert fresh_state.cognitive.tool_arguments == {}
        assert fresh_state.cognitive.pending_thought == ""
        assert fresh_state.cognitive.tool_confirmation_needed is False
        assert fresh_state.cognitive.tool_confirmed is False

    def test_does_not_touch_long_term_tool_results(self, fresh_state: AgentState):
        fresh_state.cognitive.tool_results = {"lookup_glossary": {"success": True}}
        reasoner_module.initialize_tools(fresh_state)
        assert fresh_state.cognitive.tool_results == {
            "lookup_glossary": {"success": True}
        }

    def test_pending_confirmation_with_user_input_routes_to_wait_node(
        self, fresh_state: AgentState
    ):
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = "yes"
        result = reasoner_module.initialize_tools(fresh_state)
        assert result.goto == "WAIT_USER_INPUT"

    def test_waiting_for_without_user_input_does_not_short_circuit(
        self, fresh_state: AgentState
    ):
        """waiting_for alone (no reply yet) shouldn't resume — only
        waiting_for + user_input together mean 'the user just replied'."""
        register_tool("a")
        fresh_state.waiting_for = AgentState.WaitingFor.PROBLEM_CONFIRMATION
        fresh_state.user_input = None
        result = reasoner_module.initialize_tools(fresh_state)
        assert result.goto == "top_level_router"


# ---------------------------------------------------------------------------
# topic routing
# ---------------------------------------------------------------------------


class TestTopicRouter:
    def test_unclear_top_level_pauses_for_clarification(
        self, fresh_state: AgentState
    ):
        classification = {
            "top_level": "unclear",
            "topic_changed": True,
            "second_level": "unclear",
        }

        with patch.object(
            router_module, "classify_route", return_value=classification
        ):
            result = router_module.top_level_router_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.pending_route_clarification == "top"
        assert fresh_state.waiting_for == AgentState.WaitingFor.ROUTE_CLARIFICATION
        assert "General system information" in fresh_state.cognitive.messages_to_include[0]
        assert fresh_state.cognitive.top_level_route is None

    def test_initial_route_scopes_tools_to_resolved_subgroup(
        self, fresh_state: AgentState
    ):
        tools = [
            "list_available_entities",
            "create_new_problem",
            "create_new_proposal",
            "get_context_ids",
            "lookup_glossary",
        ]
        fresh_state.cognitive.known_tools = tools
        classification = {
            "top_level": route_groups.TOP_LOCATION,
            "topic_changed": True,
            "second_level": route_groups.SUB_PROBLEM,
        }

        with patch.object(
            router_module, "classify_route", return_value=classification
        ) as classify:
            result = router_module.top_level_router_node(fresh_state)

        assert result.goto == "react_reasoner"
        assert fresh_state.cognitive.top_level_route == route_groups.TOP_LOCATION
        assert fresh_state.cognitive.second_level_route == [route_groups.SUB_PROBLEM]
        assert set(fresh_state.cognitive.enabled_tools) == {
            "list_available_entities",
            "create_new_problem",
            "get_context_ids",
        }
        classify.assert_called_once_with(fresh_state, None, None)

    def test_unclear_second_level_pauses_with_domain_scoped_tools(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.known_tools = [
            "list_available_entities",
            "create_new_problem",
            "create_new_proposal",
            "create_new_scenario",
            "get_context_ids",
        ]
        classification = {
            "top_level": route_groups.TOP_LOCATION,
            "topic_changed": True,
            "second_level": "unclear",
        }

        with patch.object(
            router_module, "classify_route", return_value=classification
        ):
            result = router_module.top_level_router_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.top_level_route == route_groups.TOP_LOCATION
        assert fresh_state.cognitive.second_level_route is None
        assert (
            fresh_state.cognitive.pending_route_clarification == "second"
        )
        assert (
            fresh_state.waiting_for == AgentState.WaitingFor.ROUTE_CLARIFICATION
        )
        assert "Problems" in fresh_state.cognitive.messages_to_include[0]
        expected_tools = route_groups.resolve_allowed_tools(
            route_groups.TOP_LOCATION, None
        ) & set(fresh_state.cognitive.known_tools)
        assert set(fresh_state.cognitive.enabled_tools) == expected_tools

    def test_same_domain_classification_can_switch_subgroup(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.top_level_route = route_groups.TOP_INDEXES
        fresh_state.cognitive.second_level_route = [route_groups.SUB_INDEX_LIST]
        fresh_state.cognitive.known_tools = [
            "get_territorial_index_list",
            "show_territorial_index_map",
            "show_territorial_index_plot",
        ]
        classification = {
            "top_level": route_groups.TOP_INDEXES,
            "topic_changed": False,
            "second_level": route_groups.SUB_INDEX_MAP,
        }

        with patch.object(
            router_module, "classify_route", return_value=classification
        ):
            result = router_module.top_level_router_node(fresh_state)

        assert result.goto == "react_reasoner"
        assert fresh_state.cognitive.second_level_route == [
            route_groups.SUB_INDEX_MAP
        ]
        assert fresh_state.cognitive.enabled_tools == [
            "get_territorial_index_list",
            "show_territorial_index_map",
        ]

    def test_topic_change_resets_old_subgroup_and_scopes_new_domain(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.top_level_route = route_groups.TOP_LOCATION
        fresh_state.cognitive.second_level_route = [route_groups.SUB_PROPOSAL]
        fresh_state.cognitive.known_tools = [
            "create_new_proposal",
            "get_system_capabilities",
            "lookup_glossary",
            "explain_workflow",
        ]
        classification = {
            "top_level": route_groups.TOP_SYSTEM_INFO,
            "topic_changed": True,
            "second_level": None,
        }

        with patch.object(
            router_module, "classify_route", return_value=classification
        ):
            result = router_module.top_level_router_node(fresh_state)

        assert result.goto == "react_reasoner"
        assert fresh_state.cognitive.top_level_route == route_groups.TOP_SYSTEM_INFO
        assert fresh_state.cognitive.second_level_route is None
        assert set(fresh_state.cognitive.enabled_tools) == {
            "get_system_capabilities",
            "lookup_glossary",
            "explain_workflow",
        }

    def test_numeric_multi_choice_resolves_second_level_without_classifier(
        self, fresh_state: AgentState
    ):
        fresh_state.cognitive.top_level_route = route_groups.TOP_LOCATION
        fresh_state.cognitive.pending_route_clarification = "second"
        fresh_state.waiting_for = AgentState.WaitingFor.ROUTE_CLARIFICATION
        fresh_state.user_input = "1 e 3"
        allowed_tools = route_groups.resolve_allowed_tools(
            route_groups.TOP_LOCATION,
            [route_groups.SUB_PROBLEM, route_groups.SUB_SCENARIO],
        )
        fresh_state.cognitive.known_tools = sorted(allowed_tools)

        with patch.object(router_module, "classify_route") as classify:
            result = router_module.resolve_clarification_reply(
                fresh_state, "second"
            )

        assert result.goto == "react_reasoner"
        assert fresh_state.cognitive.second_level_route == [
            route_groups.SUB_PROBLEM,
            route_groups.SUB_SCENARIO,
        ]
        assert set(fresh_state.cognitive.enabled_tools) == allowed_tools
        assert fresh_state.waiting_for is None
        assert fresh_state.cognitive.pending_route_clarification is None
        classify.assert_not_called()


# ---------------------------------------------------------------------------
# react_reasoner_node — tool selection
# ---------------------------------------------------------------------------


class TestReactReasonerToolSelection:
    def test_page_parameter_first_action_uses_snapshot_param_name(self, fresh_state):
        tool = create_get_configuration_parameters_tool()
        get_tool_registry().register_tool(tool)
        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = [tool.name]
        fresh_state.cognitive.top_level_route = route_groups.TOP_LOCATION
        fresh_state.cognitive.second_level_route = route_groups.SUB_SCENARIO
        fresh_state.page_context = {
            "route": "/problems/p1/proposals/pr1/scenari/s1",
            "entities": {"scenario_id": "s1", "active_tab": "Parcheggi"},
            "elements": [{
                "id": "number-1", "type": "number", "param_name": "parking_users",
                "value": 2.5,
            }],
        }
        fresh_state.add_user_message("What is this parameter?")
        response = react_step_response(
            action="tool",
            tool_name="get_configuration_parameters",
            arguments={"names": ["parking_users"]},
        )

        with patch.object(
            react_reasoning_module, "llm_interaction", return_value=response
        ) as llm:
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == "get_configuration_parameters"
        assert fresh_state.cognitive.tool_arguments == {"names": ["parking_users"]}
        prompt = llm.call_args.args[1]
        assert "param_name=" in prompt
        assert "active_tab=" in prompt
        assert "ENRICH PAGE CONTEXT BEFORE ASKING" in prompt

    def test_page_index_max_first_action_uses_single_highest_ranking_query(
        self, fresh_state
    ):
        tool = create_query_territorial_index_values_tool()
        get_tool_registry().register_tool(tool)
        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = [tool.name]
        fresh_state.cognitive.top_level_route = route_groups.TOP_INDEXES
        fresh_state.cognitive.second_level_route = route_groups.SUB_INDEX_QUERY
        fresh_state.page_context = {
            "route": "/indici",
            "entities": {
                "index_id": "tourism-index",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
            },
            "elements": [],
        }
        fresh_state.add_user_message("What is the max?")
        response = react_step_response(
            action="tool",
            tool_name="query_territorial_index_values",
            arguments={
                "index_id": "tourism-index",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "query_type": "ranking",
                "ranking_order": "highest",
                "top_n": 1,
            },
        )

        with patch.object(
            react_reasoning_module, "llm_interaction", return_value=response
        ) as llm:
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == "query_territorial_index_values"
        assert fresh_state.cognitive.tool_arguments["query_type"] == "ranking"
        assert fresh_state.cognitive.tool_arguments["ranking_order"] == "highest"
        assert fresh_state.cognitive.tool_arguments["top_n"] == 1
        assert "index_id=" in llm.call_args.args[1]

    def test_page_snapshot_without_entities_keeps_clarification_behavior(
        self, fresh_state
    ):
        register_tool("get_configuration_parameters")
        fresh_state.integrated_mode = True
        fresh_state.session_mode = "internal"
        fresh_state.cognitive.enabled_tools = ["get_configuration_parameters"]
        fresh_state.page_context = {
            "route": "/scenario",
            "elements": [{"id": "number-1", "type": "number", "value": 2.5}],
        }
        fresh_state.add_user_message("What is this parameter?")
        response = react_step_response(
            action="finish", message="Which parameter do you mean?"
        )

        with patch.object(
            react_reasoning_module, "llm_interaction", return_value=response
        ) as llm:
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.messages_to_include == ["Which parameter do you mean?"]
        assert "(none captured)" in llm.call_args.args[1]

    def test_reports_role_and_mode_restrictions_separately(
        self, fresh_state: AgentState
    ):
        register_tool("read_tool")
        get_tool_registry().register_tool(
            ToolDefinition(
                name="save_tool",
                description="d",
                category=ToolCategory.UTILITY,
                allowed_roles=("admin", "editor"),
            )
        )
        get_tool_registry().register_tool(
            ToolDefinition(
                name="internal_tool",
                description="d",
                category=ToolCategory.UTILITY,
                allowed_modes=("internal",),
            )
        )
        fresh_state.user_role = "viewer"
        fresh_state.session_mode = "standalone"
        fresh_state.cognitive.enabled_tools = ["read_tool"]

        with patch.object(
            reasoner_module, "react_step", return_value=react_step_response()
        ) as mock_react_step:
            reasoner_module.react_reasoner_node(fresh_state)

        assert mock_react_step.call_args.args[2] == ["internal_tool"]
        assert mock_react_step.call_args.args[3] == ["save_tool"]

    def test_selects_enabled_tool_and_stages_it_for_execution(
        self, fresh_state: AgentState
    ):
        register_tool(
            "lookup_glossary",
            [ToolParameter(name="query", description="d", type="string")],
        )
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(
            action="tool", tool_name="lookup_glossary", arguments={"query": "problem"}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == "lookup_glossary"
        assert fresh_state.cognitive.tool_arguments == {"query": "problem"}
        assert fresh_state.cognitive.pending_thought == "reasoning..."

    def test_rejects_tool_not_in_enabled_allowlist(self, fresh_state: AgentState):
        """Registered globally but not enabled in this context (e.g. scoped
        by integrated mode) — must not be dispatched even if the model asks."""
        register_tool("delete_problem")
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(
            action="tool", tool_name="delete_problem", arguments={}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.selected_tool is None
        assert fresh_state.cognitive.messages_to_include == [
            "I don't have enough information to answer that yet. "
            "What specific information would you like to know?"
        ]

    def test_hallucinated_tool_name_finishes_safely(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(
            action="tool", tool_name="tool_that_does_not_exist", arguments={}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.selected_tool is None

    def test_missing_tool_name_with_tool_action_finishes_safely(
        self, fresh_state: AgentState
    ):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(action="tool", tool_name=None, arguments={})

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"

    def test_missing_arguments_defaults_to_empty_dict(self, fresh_state: AgentState):
        register_tool("get_system_capabilities")
        fresh_state.cognitive.enabled_tools = ["get_system_capabilities"]
        raw = json.dumps(
            {"thought": "t", "action": "tool", "tool_name": "get_system_capabilities"}
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.tool_arguments == {}

    def test_finish_action_sets_message_and_ends_turn(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(action="finish", message="Here's your answer.")

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.messages_to_include == ["Here's your answer."]

    def test_finish_action_without_message_uses_fallback(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = json.dumps({"thought": "t", "action": "finish"})

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert fresh_state.cognitive.messages_to_include == [
            "Could you clarify your request?"
        ]

    def test_unrecognized_action_value_finishes_safely(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        raw = react_step_response(action="do_a_backflip", message="n/a")

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"

    def test_no_tools_available_still_allows_answer_from_context(
        self, fresh_state: AgentState
    ):
        # Registry has zero tools registered at all (not just zero enabled),
        # but the model can still answer from session context.
        raw = react_step_response(action="finish", message="Le località sono Fazzon.")
        with patch.object(reasoner_module, "react_step", return_value=raw) as mock_step:
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "generate_output_message"
        assert fresh_state.cognitive.messages_to_include == [
            "Le località sono Fazzon."
        ]
        mock_step.assert_called_once()

    def test_max_react_steps_forces_finish_without_calling_llm(
        self, fresh_state: AgentState
    ):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        fresh_state.cognitive.scratchpad = [
            ReActStep(tool_name=f"step_{i}")
            for i in range(fresh_state.cognitive.max_react_steps)
        ]

        with patch.object(reasoner_module, "react_step") as mock_react_step:
            result = reasoner_module.react_reasoner_node(fresh_state)

        mock_react_step.assert_not_called()
        assert result.goto == "generate_output_message"
        # The safety-valve path deliberately leaves messages_to_include
        # empty so generate_output_message falls back to synthesizing from
        # every observation collected this turn.
        assert fresh_state.cognitive.messages_to_include == []

    def test_malformed_llm_json_routes_to_error(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        with patch.object(
            reasoner_module, "react_step", return_value="not valid json {{{"
        ):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "error"
        assert fresh_state.cognitive.error_details

    def test_markdown_fenced_json_is_unwrapped(self, fresh_state: AgentState):
        """Models sometimes wrap JSON in ```json ... ``` fences despite being
        told not to — react_reasoner_node must strip that before parsing."""
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = (
            "```json\n"
            + react_step_response(
                action="tool",
                tool_name="lookup_glossary",
                arguments={"query": "scenario"},
            )
            + "\n```"
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == "lookup_glossary"

    def test_trace_step_recorded_for_each_decision(self, fresh_state: AgentState):
        register_tool("lookup_glossary")
        fresh_state.cognitive.enabled_tools = ["lookup_glossary"]
        raw = react_step_response(action="finish", message="done")

        with patch.object(reasoner_module, "react_step", return_value=raw):
            reasoner_module.react_reasoner_node(fresh_state)

        trace_steps = [
            s
            for s in fresh_state.cognitive.trace.steps
            if s.step_type == "react_thought"
        ]
        assert len(trace_steps) == 1
        assert trace_steps[0].data["action"] == "finish"


# ---------------------------------------------------------------------------
# Parametrized "correct tool for this LLM decision" table
# ---------------------------------------------------------------------------


class TestToolSelectionTable:
    """A compact table of (mocked LLM decision -> expected routing outcome),
    useful as a single place to extend when a new tool is added."""

    @pytest.mark.parametrize(
        "tool_name,arguments",
        [
            ("get_system_capabilities", {}),
            ("list_available_problems", {}),
            (
                "get_context_ids",
                {
                    "user_intent": "overtourism",
                    "source_tools": ["list_available_problems"],
                },
            ),
            ("analyze_scenario_results", {"query": "what is the KPI?"}),
            ("create_new_problem", {"name": "N", "description": "D"}),
            ("lookup_glossary", {"query": "scenario"}),
        ],
    )
    def test_each_known_tool_can_be_selected_when_enabled(
        self, fresh_state, tool_name, arguments
    ):
        register_tool(tool_name)
        fresh_state.cognitive.enabled_tools = [tool_name]
        raw = react_step_response(
            action="tool", tool_name=tool_name, arguments=arguments
        )

        with patch.object(reasoner_module, "react_step", return_value=raw):
            result = reasoner_module.react_reasoner_node(fresh_state)

        assert result.goto == "tool_executor"
        assert fresh_state.cognitive.selected_tool == tool_name
        assert fresh_state.cognitive.tool_arguments == arguments
