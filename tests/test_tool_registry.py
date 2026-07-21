import pytest

from app.tools.tool_registry import ToolRegistry, get_tool_registry, reset_tool_registry
from app.tools.tool_schema import ToolCategory, ToolDefinition


def make_tool(name="tool_a", enabled=True):
    return ToolDefinition(
        name=name, description="d", category=ToolCategory.UTILITY, enabled=enabled
    )


class TestToolRegistryCRUD:
    def test_register_and_get_tool(self):
        reg = ToolRegistry()
        tool = make_tool()
        reg.register_tool(tool)
        assert reg.get_tool("tool_a") is tool

    def test_get_missing_tool_returns_none(self):
        reg = ToolRegistry()
        assert reg.get_tool("nope") is None

    def test_register_tool_overwrites_existing(self, caplog):
        reg = ToolRegistry()
        reg.register_tool(make_tool(name="tool_a"))
        new_tool = make_tool(name="tool_a")
        reg.register_tool(new_tool)
        assert reg.get_tool("tool_a") is new_tool

    def test_register_tools_bulk(self):
        reg = ToolRegistry()
        reg.register_tools([make_tool("a"), make_tool("b")])
        assert set(reg.list_tool_names()) == {"a", "b"}

    def test_unregister_tool(self):
        reg = ToolRegistry()
        reg.register_tool(make_tool("a"))
        reg.unregister_tool("a")
        assert reg.get_tool("a") is None

    def test_unregister_missing_tool_is_noop(self):
        reg = ToolRegistry()
        reg.unregister_tool("does_not_exist")  # should not raise

    def test_list_tool_names(self):
        reg = ToolRegistry()
        reg.register_tools([make_tool("a"), make_tool("b")])
        assert set(reg.list_tool_names()) == {"a", "b"}


class TestToolRegistryFiltering:
    def test_get_all_known_tools_excludes_disabled(self):
        reg = ToolRegistry()
        reg.register_tool(make_tool("enabled_tool", enabled=True))
        reg.register_tool(make_tool("disabled_tool", enabled=False))
        known = reg.get_all_known_tools()
        assert set(known.keys()) == {"enabled_tool"}

    def test_set_tool_enabled_toggles_visibility(self):
        reg = ToolRegistry()
        reg.register_tool(make_tool("a", enabled=True))
        reg.set_tool_enabled("a", False)
        assert "a" not in reg.get_all_known_tools()
        reg.set_tool_enabled("a", True)
        assert "a" in reg.get_all_known_tools()

    def test_set_tool_enabled_on_missing_tool_is_noop(self):
        reg = ToolRegistry()
        reg.set_tool_enabled("missing", True)  # should not raise

    def test_get_context_tools_no_allowlist_returns_all_enabled(self):
        reg = ToolRegistry()
        reg.register_tools([make_tool("a"), make_tool("b")])
        assert set(reg.get_context_tools().keys()) == {"a", "b"}

    def test_get_context_tools_with_allowlist_filters(self):
        reg = ToolRegistry()
        reg.register_tools([make_tool("a"), make_tool("b"), make_tool("c")])
        result = reg.get_context_tools(allowlist=["a", "c"])
        assert set(result.keys()) == {"a", "c"}

    def test_get_context_tools_allowlist_excludes_disabled_even_if_listed(self):
        reg = ToolRegistry()
        reg.register_tool(make_tool("a", enabled=False))
        result = reg.get_context_tools(allowlist=["a"])
        assert result == {}

    def test_get_tools_for_llm_returns_tool_descriptions(self):
        reg = ToolRegistry()
        reg.register_tool(make_tool("a"))
        llm_tools = reg.get_tools_for_llm()
        assert len(llm_tools) == 1
        assert llm_tools[0]["function"]["name"] == "a"

    def test_get_tools_for_llm_respects_allowlist(self):
        reg = ToolRegistry()
        reg.register_tools([make_tool("a"), make_tool("b")])
        llm_tools = reg.get_tools_for_llm(allowlist=["a"])
        names = {t["function"]["name"] for t in llm_tools}
        assert names == {"a"}


class TestGlobalRegistry:
    def test_get_tool_registry_returns_singleton(self):
        reset_tool_registry()
        reg1 = get_tool_registry()
        reg2 = get_tool_registry()
        assert reg1 is reg2

    def test_reset_tool_registry_creates_new_instance(self):
        reg1 = get_tool_registry()
        reg1.register_tool(make_tool("a"))
        reset_tool_registry()
        reg2 = get_tool_registry()
        assert reg1 is not reg2
        assert reg2.get_tool("a") is None
