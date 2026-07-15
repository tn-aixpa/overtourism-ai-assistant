"""
Tool registry for the agentic system.
"""

from typing import Dict, List, Optional, Any
import logging

from app.tools.tool_schema import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister_tool(self, tool_name: str) -> None:
        if tool_name in self._tools:
            del self._tools[tool_name]

    def register_tools(self, tools: List[ToolDefinition]) -> None:
        for tool in tools:
            self.register_tool(tool)

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        return self._tools.get(tool_name)

    def list_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def get_all_known_tools(self) -> Dict[str, ToolDefinition]:
        return {name: tool for name, tool in self._tools.items() if tool.enabled}

    def set_tool_enabled(self, tool_name: str, enabled: bool) -> None:
        if tool_name in self._tools:
            self._tools[tool_name].enabled = enabled

    def get_context_tools(
        self, allowlist: Optional[List[str]] = None
    ) -> Dict[str, ToolDefinition]:
        tools = self.get_all_known_tools()
        if allowlist is not None:
            tools = {name: tool for name, tool in tools.items() if name in allowlist}
        return tools

    def get_tools_for_llm(
        self, allowlist: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        tools = self.get_context_tools(allowlist=allowlist)
        return [tool.to_tool_description() for tool in tools.values()]


_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def reset_tool_registry() -> None:
    global _global_registry
    _global_registry = ToolRegistry()
