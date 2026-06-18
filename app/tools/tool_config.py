"""
Tool configuration and initialization for the agentic system.

This module handles setup of the tool registry with proper user/context-based restrictions.
It provides high-level APIs for configuring which tools are available to different users.
"""

import logging
from typing import Optional

from app.tools.tool_registry import get_tool_registry, reset_tool_registry
from app.tools.agent_tools import get_all_agent_tools

logger = logging.getLogger(__name__)


class ToolConfiguration:
    """Manages tool configuration and access control."""
    
    def __init__(self):
        self.registry = get_tool_registry()
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize the tool registry with all available tools."""
        if self._initialized:
            logger.info("Tool registry already initialized")
            return
        
        logger.info("Initializing tool registry")
        
        # Register all tools
        all_tools = get_all_agent_tools()
        self.registry.register_tools(all_tools)
        
        logger.info(f"Registered {len(all_tools)} tools")
        logger.debug(f"Tool names: {self.registry.list_tool_names()}")
        
        self._initialized = True
    
    def enable_tool(self, tool_name: str, enabled: bool = True) -> None:
        """Enable or disable a tool globally."""
        self.initialize()
        self.registry.set_tool_enabled(tool_name, enabled)
        logger.info(f"Tool '{tool_name}' set to enabled={enabled}")
    
    def disable_tool(self, tool_name: str) -> None:
        """Disable a tool globally."""
        self.enable_tool(tool_name, False)
        
    def get_stats(self) -> dict:
        """Get registry statistics."""
        self.initialize()
        return self.registry.get_stats()


# Global configuration instance
_tool_config: Optional[ToolConfiguration] = None


def get_tool_configuration() -> ToolConfiguration:
    """Get or create the global tool configuration."""
    global _tool_config
    if _tool_config is None:
        _tool_config = ToolConfiguration()
    return _tool_config


def initialize_tools() -> None:
    """Initialize the tool system with default configuration."""
    config = get_tool_configuration()
    config.initialize()
    logger.info("Tool system initialized")


def reset_tools() -> None:
    """Reset the tool system (for testing)."""
    global _tool_config
    reset_tool_registry()
    _tool_config = None
    logger.info("Tool system reset")
