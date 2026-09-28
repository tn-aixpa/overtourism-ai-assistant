"""
Tool registry for the agentic system.
"""

from typing import Dict, List, Optional, Any
import logging

from app.tools.tool_schema import ToolDefinition
from app.tools.definitions import get_all_agent_tools

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
        self,
        allowlist: Optional[List[str]] = None,
        role: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, ToolDefinition]:
        """Enabled tools, narrowed by (in order): the explicit `allowlist`
        (a name allowlist, e.g. from a session's known_tools), then by
        `role`/`mode` against each tool's own allowed_roles/allowed_modes
        (see ToolDefinition.is_allowed_for). Passing role=None/mode=None
        only excludes tools whose access is actually restricted on that
        axis and needed a value to check against — an unrestricted tool
        (allowed_roles/allowed_modes is None) is never affected by what's
        passed here.
        """
        tools = self.get_all_known_tools()
        if allowlist is not None:
            tools = {name: tool for name, tool in tools.items() if name in allowlist}
        return {
            name: tool
            for name, tool in tools.items()
            if tool.is_allowed_for(role, mode)
        }

    def get_tools_for_llm(
        self,
        allowlist: Optional[List[str]] = None,
        role: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        tools = self.get_context_tools(allowlist=allowlist, role=role, mode=mode)
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


def _ensure_tool_registry() -> None:
    """Populate the tool registry if this is the first call in the process
    (mirrors initialize_tools' lazy-registration — the registry is a
    process-wide singleton, so normal chat turns may have already done
    this)."""
    registry = get_tool_registry()
    if not registry.list_tool_names():
        registry.register_tools(get_all_agent_tools())

    return registry
