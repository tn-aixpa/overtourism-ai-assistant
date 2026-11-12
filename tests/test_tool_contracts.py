"""
Contract tests over the REAL tool set (everything get_all_agent_tools()
registers), as opposed to the hand-registered toy tools used elsewhere.

They catch the drift that unit tests on single tools can't: a tool added to
the registry but not to a route group (so the reasoner can never pick it), a
route group naming a tool that no longer exists, a schema parameter the
executor can't accept (TypeError at run time), a write tool that a viewer
could select, or a widget enum with no matching implementation.

Fully offline and deterministic.
"""

import inspect

import pytest

from app.agent.nodes import route_groups as rg
from app.agent.nodes.tool_executor import (
    CONFIRMATION_REQUIRED_TOOLS,
    get_tool_executor,
)
from app.agent.state import TIERS_REQUIRING_CONSENT
from app.tools.tool_registry import _ensure_tool_registry
from app.tools.tool_schema import ALL_SESSION_MODES, ALL_USER_ROLES

# Retired aliases replaced by list_available_entities.
RETIRED_LIST_TOOLS = {
    "list_available_problems",
    "list_available_proposals",
    "list_available_scenarios",
}

WRITE_TOOLS = set(CONFIRMATION_REQUIRED_TOOLS)

# Declared-in-schema parameters that the executor does not accept today.
# strict xfail: the day this is fixed, the test turns red and reminds you to
# remove the entry.
KNOWN_SCHEMA_EXECUTOR_GAPS = {
    ("create_new_problem", "links"): (
        "PROBLEM_PARAMETERS declares 'links' but execute_create_new_problem "
        "has no such argument (and the backend tool has no field for it): "
        "the call fails with TypeError. Either support it end-to-end or "
        "drop it from the create schema."
    ),
}


@pytest.fixture
def tools():
    registry = _ensure_tool_registry()
    return registry.get_all_known_tools()


def _routed_tool_names() -> set[str]:
    """Every tool name any (top level, sub level) combination can expose."""
    names: set[str] = set(rg._LOCATION_SHARED_TOOLS)
    for top in (rg.TOP_SYSTEM_INFO, rg.TOP_GENERAL, rg.TOP_LOCATION, rg.TOP_INDEXES):
        names |= rg.resolve_allowed_tools(top, None) or set()
    for top, groups in rg.SUBLEVELS.items():
        for sub in groups:
            names |= rg.resolve_allowed_tools(top, sub) or set()
    return names


# ---------------------------------------------------------------------------
# Registry <-> route table <-> executors
# ---------------------------------------------------------------------------


class TestRegistryConsistency:
    def test_every_tool_named_in_a_route_group_is_registered(self, tools):
        missing = _routed_tool_names() - set(tools)
        assert not missing, f"route_groups references unknown tools: {sorted(missing)}"

    def test_every_enabled_tool_is_reachable_from_some_route(self, tools):
        unrouted = {n for n in tools if n not in _routed_tool_names()}
        assert not unrouted, f"Unrouted tools: {sorted(unrouted)}"

    def test_every_enabled_tool_has_an_executor(self, tools):
        missing = [n for n in tools if get_tool_executor(n) is None]
        assert not missing, f"tools without an executor: {missing}"

    def test_retired_list_tools_are_not_registered_or_executable(self, tools):
        for name in RETIRED_LIST_TOOLS:
            assert name not in tools
            assert get_tool_executor(name) is None

    def test_tool_names_descriptions_and_categories_are_filled_in(self, tools):
        for name, tool in tools.items():
            assert tool.name == name
            assert tool.description and tool.description.strip(), name
            assert tool.category is not None, name

    def test_every_tool_has_a_valid_agent_tier(self, tools):
        valid = {"executor", "operative", "methodological", "exploitative"}
        for name, tool in tools.items():
            assert str(getattr(tool.agent_tier, "value", tool.agent_tier)) in valid, name


# ---------------------------------------------------------------------------
# Schema <-> executor signature
# ---------------------------------------------------------------------------


def _accepted_and_required(executor):
    params = inspect.signature(executor).parameters
    has_kwargs = any(p.kind is p.VAR_KEYWORD for p in params.values())
    accepted = {
        k for k, p in params.items() if k != "state" and p.kind is not p.VAR_KEYWORD
    }
    required = {
        k
        for k, p in params.items()
        if k != "state"
        and p.default is p.empty
        and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
    }
    return accepted, required, has_kwargs


def _all_tool_names():
    registry = _ensure_tool_registry()
    return sorted(registry.get_all_known_tools())


class TestSchemaMatchesExecutor:
    @pytest.mark.parametrize("name", _all_tool_names())
    def test_executor_accepts_every_declared_parameter(self, name, request):
        tools = _ensure_tool_registry().get_all_known_tools()
        accepted, _, has_kwargs = _accepted_and_required(get_tool_executor(name))
        for param in tools[name].parameters:
            if (name, param.name) in KNOWN_SCHEMA_EXECUTOR_GAPS:
                request.applymarker(
                    pytest.mark.xfail(
                        strict=True, reason=KNOWN_SCHEMA_EXECUTOR_GAPS[(name, param.name)]
                    )
                )
            assert param.name in accepted or has_kwargs, (
                f"{name}: schema declares '{param.name}' but the executor would "
                f"raise TypeError when the model passes it"
            )

    @pytest.mark.parametrize("name", _all_tool_names())
    def test_required_executor_args_are_required_in_the_schema(self, name):
        """If the executor needs an argument the schema marks optional, the
        pre-execution validation passes and the call then dies with a
        TypeError instead of a clear 'missing parameter' question."""
        tools = _ensure_tool_registry().get_all_known_tools()
        _, required, _ = _accepted_and_required(get_tool_executor(name))
        schema_required = {p.name for p in tools[name].parameters if p.required}
        undeclared = required - schema_required
        assert not undeclared, f"{name}: executor requires {sorted(undeclared)}"

    @pytest.mark.parametrize("name", _all_tool_names())
    def test_parameter_names_are_unique(self, name):
        tools = _ensure_tool_registry().get_all_known_tools()
        names = [p.name for p in tools[name].parameters]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# What the LLM is shown
# ---------------------------------------------------------------------------


class TestLlmToolDescriptions:
    @pytest.mark.parametrize("role", sorted(ALL_USER_ROLES))
    @pytest.mark.parametrize("mode", ["standalone", "internal"])
    def test_descriptions_are_well_formed_for_every_role_and_mode(self, role, mode):
        registry = _ensure_tool_registry()
        descriptions = registry.get_tools_for_llm(role=role, mode=mode)
        assert descriptions, f"no tools at all for {role}/{mode}"
        seen = set()
        for d in descriptions:
            fn = d["function"]
            assert fn["name"] not in seen
            seen.add(fn["name"])
            schema = fn["parameters"]
            assert schema["type"] == "object"
            assert set(schema["required"]) <= set(schema["properties"])
            for prop in schema["properties"].values():
                assert prop["type"] in {
                    "string", "integer", "number", "boolean", "object", "array",
                }
                assert prop["description"].strip()

    def test_enum_parameters_have_non_empty_enums(self, tools):
        for name, tool in tools.items():
            for p in tool.parameters:
                if p.schema and "enum" in p.schema:
                    assert p.schema["enum"], f"{name}.{p.name}"


# ---------------------------------------------------------------------------
# Safety policy encoded in the tool metadata
# ---------------------------------------------------------------------------


class TestToolPolicy:
    def test_every_write_tool_exists_and_is_restricted_to_editors(self, tools):
        for name in WRITE_TOOLS:
            assert name in tools, f"{name} is in CONFIRMATION_REQUIRED_TOOLS but not registered"
            roles = tools[name].allowed_roles
            assert roles is not None and "viewer" not in roles, name

    def test_every_tool_tagged_write_requires_confirmation(self, tools):
        tagged = {n for n, t in tools.items() if "write" in (t.tags or [])}
        unguarded = tagged - CONFIRMATION_REQUIRED_TOOLS - {"create_new_temp_scenario"}
        assert not unguarded, (
            f"write-tagged tools that skip the confirmation step: {sorted(unguarded)}"
        )

    def test_viewer_cannot_select_any_write_or_exploitative_tool(self):
        registry = _ensure_tool_registry()
        for mode in ("standalone", "internal"):
            visible = set(registry.get_context_tools(role="viewer", mode=mode))
            exploitative = {
                n for n, t in registry.get_all_known_tools().items()
                if str(getattr(t.agent_tier, "value", t.agent_tier)) in TIERS_REQUIRING_CONSENT
            }
            assert not (visible & WRITE_TOOLS), mode
            assert not (visible & exploitative), mode

    def test_editor_can_select_write_and_exploitative_tools(self):
        registry = _ensure_tool_registry()
        visible = set(registry.get_context_tools(role="editor", mode="standalone"))
        assert {"create_new_problem", "general_question_response", "web_search"} <= visible

    def test_widget_tools_are_standalone_only(self):
        registry = _ensure_tool_registry()
        internal = set(registry.get_context_tools(role="admin", mode="internal"))
        standalone = set(registry.get_context_tools(role="admin", mode="standalone"))
        widgets = {"show_analysis_widget", "show_territorial_index_map", "show_territorial_index_plot"}
        assert widgets <= standalone
        assert not (widgets & internal)

    def test_exploitative_tools_are_only_on_the_general_and_system_info_routes(self, tools):
        exploitative = {
            n for n, t in tools.items()
            if str(getattr(t.agent_tier, "value", t.agent_tier)) in TIERS_REQUIRING_CONSENT
        }
        for top in (rg.TOP_LOCATION, rg.TOP_INDEXES):
            routed = rg.resolve_allowed_tools(top, None) or set()
            assert not (routed & exploitative), top

    def test_system_info_can_escalate_to_the_exploitative_general_tool(self):
        """system_info's guideline says to fall back to general_question_response
        when the glossary and workflow document don't cover a question; the
        route must actually allow it (and the grounded tools before it)."""
        allowed = rg.resolve_allowed_tools(rg.TOP_SYSTEM_INFO, None)
        assert {
            "get_system_capabilities", "lookup_glossary", "explain_workflow",
            "general_question_response",
        } <= allowed

    def test_off_topic_exposes_no_tools(self):
        """The guardrail verdict is not a routable domain."""
        assert rg.TOP_OFF_TOPIC not in rg.TOP_LEVEL_LABELS


# ---------------------------------------------------------------------------
# Schema enums <-> implementation tables
# ---------------------------------------------------------------------------


class TestWidgetVocabulary:
    def test_every_show_widget_type_has_a_spec_and_response_text(self, tools):
        from app.tools.executors import analysis_widgets as aw

        enum = next(
            p.schema["enum"] for p in tools["show_analysis_widget"].parameters
            if p.name == "widget_type"
        )
        assert set(enum) == set(aw._WIDGET_SPECS)
        assert set(enum) <= set(aw._RESPONSE_TEXT)

    def test_every_explainable_widget_type_has_an_explanation(self, tools):
        from app.tools.executors import analysis_widgets as aw

        enum = next(
            p.schema["enum"] for p in tools["explain_widget"].parameters
            if p.name == "widget_type"
        )
        assert set(enum) == set(aw._WIDGET_EXPLANATIONS)
