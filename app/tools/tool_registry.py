"""
Tool registry for the agentic system.

Manages available tools and provides context-aware tool filtering.
Allows restricting tools based on user roles, subscription levels, or other contexts.
"""

from typing import Dict, List, Optional, Set,  Any
import logging

from app.tools.tool_schema import ToolDefinition, ToolCategory

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all available tools.
    
    Supports:
    - Dynamic tool registration and unregistration
    - Context-aware tool filtering
    - Tool access control based on user/role/subscription
    - Tool discovery and introspection
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._tool_access_control: Dict[str, Set[str]] = {}  # tool_name -> set of allowed contexts
        
    # ---- Registration ----
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool in the registry."""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def unregister_tool(self, tool_name: str) -> None:
        """Unregister a tool from the registry."""
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info(f"Unregistered tool: {tool_name}")
    
    def register_tools(self, tools: List[ToolDefinition]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register_tool(tool)
    
    # ---- Discovery ----
    
    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(tool_name)
    
    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """Get all registered tools."""
        return dict(self._tools)
    
    def list_tool_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_tools_by_category(self, category: ToolCategory) -> Dict[str, ToolDefinition]:
        """Get all tools in a specific category."""
        return {
            name: tool 
            for name, tool in self._tools.items() 
            if tool.category == category
        }
    
    def get_tools_by_tag(self, tag: str) -> Dict[str, ToolDefinition]:
        """Get all tools with a specific tag."""
        return {
            name: tool 
            for name, tool in self._tools.items() 
            if tag in tool.tags
        }
    
    # ---- Access Control ----
           
    def set_tool_enabled(self, tool_name: str, enabled: bool) -> None:
        """Enable or disable a tool globally."""
        if tool_name in self._tools:
            self._tools[tool_name].enabled = enabled
            logger.info(f"Tool '{tool_name}' enabled={enabled}")
    
    def get_all_enabled_tools(self) -> Dict[str, ToolDefinition]:
        """Get all enabled tools."""
        return {
            name: tool 
            for name, tool in self._tools.items() 
            if tool.enabled
        }
    
    # ---- Context-Aware Filtering ----
    
    def get_context_tools(
        self, 
        active_context: Optional[str] = None,
    ) -> Dict[str, ToolDefinition]:
        """
        Get tools available in a specific context.
        
        Args:
            active_context: Type of active context (e.g., "problem", "proposal", "scenario")
            
        Returns:
            Dictionary of available tools for this context
        """
        # Start with user-allowed tools
        tools = self.get_all_enabled_tools()
        
        # Filter by active context if provided
        if active_context:
            tools = {
                name: tool 
                for name, tool in tools.items() 
                if tool.requires_context is None or tool.requires_context == active_context
            }
        
        return tools
    
    # ---- Tool Description Format ----
    
    def get_tools_for_llm(
        self,
        active_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get tools formatted for LLM tool calling.
        
        Returns list of tool definitions in Claude/OpenAI format.
        """
        tools = self.get_context_tools(active_context)
        return [
            tool.to_tool_description() 
            for tool in tools.values()
        ]
    
    def get_tools_description(
        self,
        active_context: Optional[str] = None,
    ) -> str:
        """
        Get human-readable description of available tools.
        
        Useful for prompts and debugging.
        """
        tools = self.get_context_tools(active_context)
        
        if not tools:
            return "No tools available."
        
        lines = ["Available tools:"]
        for name, tool in sorted(tools.items()):
            lines.append(f"\n- **{name}**: {tool.description}")
            if tool.long_description:
                lines.append(f"  {tool.long_description}")
        
        return "\n".join(lines)
    
    # ---- Statistics ----
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        tools_by_category = {}
        for category in ToolCategory:
            tools_by_category[category.value] = len(
                self.get_tools_by_category(category)
            )
        
        return {
            "total_tools": len(self._tools),
            "enabled_tools": len(self.get_all_enabled_tools()),
            "tools_by_category": tools_by_category,
        }


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def reset_tool_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _global_registry
    _global_registry = ToolRegistry()
